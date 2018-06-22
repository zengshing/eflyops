# ~*~ coding: utf-8 ~*~
from common.utils import get_logger, get_object_or_none
from .models import Task, AdHoc, Command

logger = get_logger(__file__)


def get_task_by_id(task_id):
    return get_object_or_none(Task, id=task_id)


def update_or_create_ansible_task(
        task_name, hosts, tasks,
        interval=None, crontab=None, is_periodic=False,
        callback=None, pattern='all', options=None,
        run_as_admin=False, run_as="", become_info=None,
        created_by=None, module=None, tasktype=None,
    ):
    if not hosts or not tasks or not task_name:
        return

    defaults = {
        'name': task_name,
        'interval': interval,
        'crontab': crontab,
        'is_periodic': is_periodic,
        'callback': callback,
        'created_by': created_by,
    }

    if tasktype == 'adhoc' or tasktype is None:
        created = False
        task, _ = Task.objects.update_or_create(
            defaults=defaults, name=task_name,
        )

        adhoc = task.latest_adhoc
        new_adhoc = AdHoc(task=task, pattern=pattern,
                          run_as_admin=run_as_admin,
                          run_as=run_as)
        new_adhoc.hosts = hosts
        new_adhoc.tasks = tasks
        new_adhoc.options = options
        new_adhoc.become = become_info

        if not adhoc or adhoc != new_adhoc:
            print("Task create new adhoc: {}".format(task_name))
            new_adhoc.save()
            task.latest_adhoc = new_adhoc
            created = True
        return task, created

#    elif tasktype == 'playbook':
#        created = False
#        task, _ = Task.objects.update_or_create(
#            defaults=defaults, name=task_name,
#        )
#
#        playbook = task.latest_playbook
#        new_playbook = PLAYBOOK(task=task, pattern=pattern,
#                          run_as_admin=run_as_admin,
#                          run_as=run_as)
#        new_playbook.hosts = hosts
#        new_playbook.tasks = tasks
#        new_playbook.options = options
#        new_playbook.become = become_info
#
#        if not playbook or playbook != new_playbook:
#            print("Task create new playbook: {}".format(task_name))
#            new_adhoc.save()
#            task.latest_playbook = new_playbook
#            created = True
#        return task, created
#
    elif tasktype == 'command':
        created = False
        task, _ = Task.objects.update_or_create(
            defaults=defaults, name=task_name,
        )

        command = task.latest_command
        new_command = Command(task=task, pattern=pattern,
                          run_as_admin=run_as_admin,
                          run_as=run_as)
        new_command.hosts = hosts
        new_command.tasks = tasks
        new_command.module = module
        new_command.options = options
        new_command.become = become_info

        if not command or command != new_command:
            print("Task create new command: {}".format(task_name))
            new_command.save()
            task.latest_command = new_command
            created = True
        return task, created
