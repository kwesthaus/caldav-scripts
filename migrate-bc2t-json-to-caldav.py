#!/usr/bin/env python

import caldav
import json
import uuid
import argparse

# so far this script handles the title, description, completion status, priority, and subtasks
# other metadata is lost
# probably only other thing I care about is reminders and due date?
#
# also, this function does not recurse. if you want to migrate subtasks, you need to call this function for the parent
# and each of the subtasks separately
def migrate_task(calendar, bc2_title, bc2_description, bc2_id, bc2_status, bc2_priority, parent_caldav_uid):
    print(f"migrating {bc2_title[:8]}...")
    # even distribution
    # ical_priority = 5 - (2*bc2_priority)
    #
    # keep high and medium high, everything else to low
    if bc2_priority < 0:
        bc2_priority = 0
    ical_priority = 7 - (2*bc2_priority)
    res = None
    # python-caldav uses the uuid module to generate a uid when creating a new task, we will do the same
    # https://github.com/python-caldav/caldav/blob/674c223fe2dc775a47f4cba8fe499d3d5fda757e/caldav/lib/vcal.py#LL144C34-L144C45
    this_uid = str(uuid.uuid1())

    print(f"this_uid: {this_uid}, parent_caldav_uid: {parent_caldav_uid}")

    # call graph: save_todo() -> self._use_or_create_ics() -> vcal.create_ical()
    # create_ical() uses the "parent" and "child" keys to determine links
    # https://github.com/python-caldav/caldav/blob/674c223fe2dc775a47f4cba8fe499d3d5fda757e/caldav/lib/vcal.py#L172
    if parent_caldav_uid:
        if bc2_status:
            res = calendar.save_todo(
                summary=bc2_title,
                description=bc2_description,
                STATUS='COMPLETED',
                # percent_complete=100,
                priority=ical_priority,
                parent=parent_caldav_uid,
                uid=this_uid,
            )
        else:
            res = calendar.save_todo(
                summary=bc2_title,
                description=bc2_description,
                priority=ical_priority,
                parent=parent_caldav_uid,
                uid=this_uid,
            )
    else:
        if bc2_status:
            res = calendar.save_todo(
                summary=bc2_title,
                description=bc2_description,
                STATUS='COMPLETED',
                # percent_complete=100,
                priority=ical_priority,
                uid=this_uid,
            )
        else:
            res = calendar.save_todo(
                summary=bc2_title,
                description=bc2_description,
                priority=ical_priority,
                uid=this_uid,
            )
    return this_uid


def main():

    parser = argparse.ArgumentParser(description='Read tasks from a bc2t file and migrate them to a caldav server')
    parser.add_argument('--credential-file', type=argparse.FileType('r'), required=True)
    parser.add_argument('--input-bc2t-file', type=argparse.FileType('r'), required=True)
    parser.add_argument('--debug-limit', type=int)
    args = parser.parse_args()

    creds = json.load(args.credential_file)

    # create a client, use it to get a reference to the task list we are migrating to
    with caldav.DAVClient(
            url=creds['url'],
            username=creds['username'],
            password=creds['password'],
    ) as client:
        my_principal = client.principal()

        tech_cal = my_principal.calendar('Tech')

        print(tech_cal.name)
        print(tech_cal.get_supported_components())

        created_tasks = set()

        # iterate over the json file we already have from bc2
        j = json.load(args.input_bc2_file)

        ctr = 0
        for task in j:
            ctr += 1
            if not ctr % 100:
                print()
                print()
                print(f"completed {ctr} so far")
                print()
                print()
            if args.debug_limit and ctr >= args.debug_limit:
                return

            if task['id'] in created_tasks:
                print(f"skipping double: {task['title'][:8]}")
                continue
            created_tasks.add(task['id'])
            uid = [migrate_task(tech_cal, task['title'], task['description'], task['id'], task['status'], task['priority'], None)]

            if task['hasSubTasks']:
                for child in task['subTasks']:
                    if child['id'] in created_tasks:
                        print(f"skipping double: {child['title'][:8]}")
                        continue
                    created_tasks.add(child['id'])
                    migrate_task(tech_cal, child['title'], child['description'], child['id'], child['status'], child['priority'], uid)

        print(f"migrated {ctr} tasks")


if __name__ == "__main__":
    main()

