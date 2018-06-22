# ~*~ coding: utf-8 ~*~
import json
import re
import os

from celery import shared_task
from django.core.cache import cache
from django.utils.translation import ugettext as _

from ..common.celery_log import get_celery_logger

from ops.celery import app as celery_app

from .models import SystemUser, AdminUser, Asset

@shared_task
def execute_shell_command_util(assets, command, tasktype='command', task_name=None, module=None):
    """
    Using ansible api to execute shell command in remote machines
    :param assets:  asset seq
    :param task_name: task_name running
    :param command: shell command to execute
    :param module: ansible shell module, by default is shell
    :return: result summary ['contacted': {}, 'dark': {}]
    """
    from ops.utils import update_or_create_ansible_task
    if task_name is None:
        # task_name = _("Update some assets hardware info")
        task_name = _("test execute shell command")
    hostname_list = [asset.hostname for asset in assets if asset.is_active and asset.is_unixlike()]
    if not hostname_list:
        logger.info("Not hosts get, may be asset is not active or not unixlike platform")
        return {}
    task, created = update_or_create_ansible_task(
        task_name, hosts=hostname_list, tasks=tasks, tasktype=tasktype, pattern='all',
        options=const.TASK_OPTIONS, run_as_admin=True, created_by='System',
    )
    result = task.run()
    return result

@shared_task
def test_ls_root(asset, command):
    task_name = _("ls root dictory")
    command = 'ls /root'
    return execute_shell_command_util(task_name=task_name, [asset], [command])
