#!/usr/bin/env python

import caldav
import json
import uuid

creds = None
with open('../migadu-creds.json', 'r') as c:
    creds = json.load(c)

DEBUG_LIMIT = False
TEST_MAX = 50

created_tasks = set()

# so far this script handles the title, description, completion status, priority, and subtasks
# other metadata is lost
# probably only other thing I care about is reminders and due date?
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
    # create a client, use it to get a reference to the task list we are migrating to
    with caldav.DAVClient(
            url=creds['url'],
            username=creds['username'],
            password=creds['password'],
    ) as client:
        my_principal = client.principal()
        calendars = my_principal.calendars()
        tech_cal = None
        for c in calendars:
            print(f"{c.name} {c.url}")
            if c.name == "Tech":
                tech_cal = c

        print(tech_cal.name)
        print(tech_cal.get_supported_components())


        # iterate over the json file we already have from bc2
        with open('Tech-tasks.json', 'r') as f:
            j = json.load(f)

            ctr = 0
            for task in j:
                ctr += 1
                if not ctr % 100:
                    print()
                    print()
                    print(f"completed {ctr} so far")
                    print()
                    print()
                if DEBUG_LIMIT and ctr >= TEST_MAX:
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

