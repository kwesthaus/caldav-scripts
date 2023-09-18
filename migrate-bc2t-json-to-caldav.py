#!/usr/bin/env python

import caldav
import json
import uuid
import argparse
import datetime

# so far this script handles the title, description, completion status, priority, and subtasks
# other metadata is lost
# probably only other thing I care about is reminders and due date?
#
# also, this function does not recurse. if you want to migrate subtasks, you need to call this function for the parent
# and each of the subtasks separately
def migrate_task(calendar, bc2_title, bc2_description, bc2_id, bc2_status, bc2_priority, parent_uid, bc2_duetime):
    print(f"migrating {bc2_title[:8]}...")

    # id
    # python-caldav uses the uuid module to generate a uid when creating a new task, we will do the same
    # https://github.com/python-caldav/caldav/blob/674c223fe2dc775a47f4cba8fe499d3d5fda757e/caldav/lib/vcal.py#LL144C34-L144C45
    this_uid = str(uuid.uuid1())

    # status
    if bc2_status:
        ical_status = 'COMPLETED'
    else:
        ical_status = None

    # priority
    # 1-4 is is high, 5 is medium, 6-9 is low
    # even distribution
    # ical_priority = 5 - (2*bc2_priority)
    #
    # another distribution: keep high and medium-high, everything else to low
    if bc2_priority < 0:
        bc2_priority = 0
    ical_priority = 7 - (2*bc2_priority)

    # parent
    print(f"this_uid: {this_uid}, parent_caldav_uid: {parent_caldav_uid}")
    if parent_uid:
        parent_caldav_uid = parent_uid
    else:
        # has to be iterable so we use [] instead of None
        parent_caldav_uid = []

    # due
    if bc2_duetime == 9223372036854775807:
        duedate = None
    else:
        duedate = datetime.date.fromtimestamp(bc2_duetime // 1000)

    # call graph: save_todo() -> self._use_or_create_ics() -> vcal.create_ical()
    # create_ical() uses the "parent" and "child" keys to determine links
    # https://github.com/python-caldav/caldav/blob/674c223fe2dc775a47f4cba8fe499d3d5fda757e/caldav/lib/vcal.py#L172
    res = calendar.save_todo(
        summary=bc2_title,
        description=bc2_description,
        STATUS=ical_status,
        priority=ical_priority,
        parent=parent_caldav_uid,
        uid=this_uid,
        due=duedate,
    )
    return this_uid


def main():

    parser = argparse.ArgumentParser(description='Read tasks from a bc2t file and migrate them to a caldav server')
    parser.add_argument('--credential-file', type=argparse.FileType('r'), required=True)
    parser.add_argument('--input-bc2t-file', type=argparse.FileType('r'), required=True)
    parser.add_argument('--debug-limit', type=int)
    args = parser.parse_args()

    # bc2t file is just 2 json lists (1 for tasks and 1 for reminders) with a special separator, "****///****"
    creds = json.load(args.credential_file)
    (tasks, reminders) = args.input_bc2t_file.read().replace('\n', '').split('****///****')
    j_tasks = json.loads(tasks)
    j_reminders = json.loads(reminders)

    # create a client
    with caldav.DAVClient(
            url=creds['url'],
            username=creds['username'],
            password=creds['password'],
    ) as client:
        my_principal = client.principal()

        created_tasks = set()
        list_actions = {}
        curr_list = None

        # iterate over the list of tasks we already have from bc2
        ctr = 0
        for task in j_tasks:
            ctr += 1
            if not ctr % 100:
                print()
                print()
                print(f"completed {ctr} so far")
                print()
                print()
            if args.debug_limit and ctr >= args.debug_limit:
                return

            task_list_name = task['collectionName']
            if task_list_name not in list_actions:
                try:
                    curr_list = my_principal.calendar(task_list_name)
                    print(f'List {task_list_name} already exists, do you want to add to it or skip items in that list?')
                    action = None
                    while action != 'add' and action != 'skip':
                        action = input('"add" or "skip": ').strip()
                    list_actions[task_list_name] = action
                except caldav.lib.error.NotFoundError as e:
                    print(f'List {task_list_name} does not exist yet, do you want to create it or skip items in that list?')
                    action = None
                    while action != 'create' and action != 'skip':
                        action = input('"create" or "skip": ').strip()
                    if action == 'skip':
                        list_actions[task_list_name] = action
                    else:
                        curr_list = my_principal.make_calendar(name=task_list_name, supported_calendar_component_set=['VTODO'])
                        list_actions[task_list_name] = 'add'
            if list_actions[task_list_name] == 'skip':
                print(f"skipping item in list {task_list_name}")
                continue

            if task['id'] in created_tasks:
                print(f"skipping double: {task['title'][:8]}")
                continue

            created_tasks.add(task['id'])
            uid = [migrate_task(curr_list, task['title'], task['description'], task['id'], task['status'], task['priority'], None, task['dtstart'])]

            if task['hasSubTasks']:
                for child in task['subTasks']:
                    if child['id'] in created_tasks:
                        print(f"skipping double: {child['title'][:8]}")
                        continue
                    created_tasks.add(child['id'])
                    migrate_task(curr_list, child['title'], child['description'], child['id'], child['status'], child['priority'], uid, task['dtstart'])

        print(f"migrated {ctr} tasks")


if __name__ == "__main__":
    main()

