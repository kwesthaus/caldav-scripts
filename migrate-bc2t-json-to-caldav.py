#!/usr/bin/env python

import caldav
import json
import uuid
import argparse
import datetime

# this function does not recurse. if you want to migrate subtasks, you need to call this function for the parent
# and each of the subtasks separately
def migrate_single_task(calendar, bc2_task, parent_uid, reminders):
    print(f"migrating {bc2_task['title'][:8]}...")
    caldav_task = {}

    # title
    caldav_task['summary'] = bc2_task['title']

    # description
    caldav_task['description'] = bc2_task['description']

    # id
    # python-caldav uses the uuid module to generate a uid when creating a new task, we will do the same
    # https://github.com/python-caldav/caldav/blob/674c223fe2dc775a47f4cba8fe499d3d5fda757e/caldav/lib/vcal.py#LL144C34-L144C45
    caldav_task['uid'] = str(uuid.uuid1())

    # status
    if bc2_task['status']:
        caldav_task['STATUS'] = 'COMPLETED'
    else:
        caldav_task['STATUS'] = None

    # priority
    # for caldav 1-4 is is high, 5 is medium, 6-9 is low
    # even distribution
    # ical_priority = 5 - (2*bc2_priority)
    #
    # another distribution: keep high and medium-high, everything else to low
    if bc2_task['priority'] < 0:
        bc2_task['priority'] = 0
    caldav_task['priority'] = 7 - (2*bc2_task['priority'])

    # parent
    if parent_uid:
        caldav_task['parent'] = [parent_uid]
    else:
        # has to be iterable so we use [] instead of None
        caldav_task['parent'] = []
    print(f"this uid: {caldav_task['uid']}, parent uid: {caldav_task['parent']}")

    # due
    if bc2_task['dtstart'] == 0x7fffffffffffffff:
        caldav_task['due'] = None
    else:
        # original value is milliseconds from epoch
        # just get the day, forget about specific time/timezone
        caldav_task['due'] = datetime.date.fromtimestamp(bc2_task['dtstart'] // 1000)

    # call graph: save_todo() -> self._use_or_create_ics() -> vcal.create_ical()
    # create_ical() uses the "parent" and "child" keys to determine links
    # https://github.com/python-caldav/caldav/blob/674c223fe2dc775a47f4cba8fe499d3d5fda757e/caldav/lib/vcal.py#L172
    res = calendar.save_todo(**caldav_task)

    # reminder
    for reminder in reminders:
        res.vobject_instance.vtodo.add('valarm')
        res.vobject_instance.vtodo.valarm_list[-1].add('action').value = 'DISPLAY'
        # note the negatives!
        if reminder['minutes'] > 0:
            res.vobject_instance.vtodo.valarm_list[-1].add('trigger').value = datetime.timedelta(minutes=-reminder['minutes'])
        else:
            t_day = caldav_task['due']
            t_start = datetime.time(0, 0)
            t_time = datetime.timedelta(minutes=-reminder['minutes'])
            t_dt = datetime.datetime.combine(t_day, t_start) + t_time
            res.vobject_instance.vtodo.valarm_list[-1].add('trigger').value = t_dt
        res.save()

    return caldav_task


def main():

    parser = argparse.ArgumentParser(description='Read tasks from a bc2t file and migrate them to a caldav server')
    parser.add_argument('-c', '--credential-file', type=argparse.FileType('r'), required=True)
    parser.add_argument('-i', '--input-bc2t-file', type=argparse.FileType('r'), required=True)
    parser.add_argument('--debug-limit', type=int)
    args = parser.parse_args()

    creds = json.load(args.credential_file)

    # bc2t file is just 2 json lists (1 for tasks and 1 for reminders) with a special separator, "****///****"
    # separator and reminders will not be included if there are none
    # my export of all tasks also had multiple commas in a row in the reminders section which is not proper json
    # the below handles 3 commas in a row (the max in my file) but YMMV
    input_bc2t_strs = args.input_bc2t_file.read().replace(',,,', ',,').replace(',,', ',').replace('\n', '').split('****///****')
    j_tasks = json.loads(input_bc2t_strs[0])
    if len(input_bc2t_strs) > 1:
        j_reminders = json.loads(input_bc2t_strs[1])
        # make it easy to search reminders later when we are iterating over tasks
        reminders_by_task_uid = {}
        for reminder in j_reminders:
            if reminder['itemId'] in reminders_by_task_uid:
                reminders_by_task_uid[reminder['itemId']].append(reminder)
            else:
                reminders_by_task_uid[reminder['itemId']] = [reminder]
    else:
        reminders_by_task_uid = {}

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

            # get or make appropriate caldav list for this task, and give user choice of action for all items in this list
            # we only check this for parents, not nested tasks, so we are making the assumption that children are in the same list as their parents
            # (I have a hard time imagining a case where that wouldn't happen, but just making assumptions explicit here)
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

            # subtasks show up both under their parent and on their own, so need to keep track of and avoid duplicates
            if task['id'] in created_tasks:
                print(f"skipping double: {task['title'][:8]}")
                continue
            created_tasks.add(task['id'])

            created_task = migrate_single_task(curr_list, task, None, reminders_by_task_uid.get(task['id'], []))

            # this pattern only handles 1 level of nesting, which is ok for my bc2t files
            if task['hasSubTasks']:
                for child in task['subTasks']:
                    if child['id'] in created_tasks:
                        print(f"skipping double: {child['title'][:8]}")
                        continue
                    created_tasks.add(child['id'])
                    migrate_single_task(curr_list, child, created_task['uid'], reminders_by_task_uid.get(child['id'], []))

        print(f"migrated {ctr} tasks")


if __name__ == "__main__":
    main()

