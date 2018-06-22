# ~*~ coding: utf-8 ~*~

import json
import uuid
import os
import time
import datetime

import time
from celery import current_task
from django.db import models
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

from common.utils import get_signer, get_logger
from common.celery import delete_celery_periodic_task, create_or_update_celery_periodic_tasks, \
disable_celery_periodic_task
from .ansible import AdHocRunner, PlayBookRunner, CommandRunner, AnsibleError
from .inventory import JMSInventory

__all__ = ["Task", "AdHoc", "AdHocRunHistory", "Command", "CMDRunHistory"]


logger = get_logger(__file__)
signer = get_signer()


class Task(models.Model):
    """
    This task is different ansible task, Task like 'push system user', 'get asset info' ..
    One task can have some versions of adhoc, run a task only run the latest version adhoc
    """
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    name = models.CharField(max_length=128, unique=True, verbose_name=_('Name'))
    interval = models.IntegerField(verbose_name=_("Interval"), null=True, blank=True, help_text=_("Units: seconds"))
    crontab = models.CharField(verbose_name=_("Crontab"), null=True, blank=True, max_length=128, help_text=_("5 * * * *"))
    is_periodic = models.BooleanField(default=False)
    callback = models.CharField(max_length=128, blank=True, null=True, verbose_name=_("Callback"))  # Callback must be a registered celery task
    is_deleted = models.BooleanField(default=False)
    comment = models.TextField(blank=True, verbose_name=_("Comment"))
    created_by = models.CharField(max_length=128, blank=True, null=True, default='')
    date_created = models.DateTimeField(auto_now_add=True)
    __latest_adhoc = None
    __latest_playbook = None
    __latest_command = None


    @property
    def short_id(self):
        return str(self.id).split('-')[-1]

    @property
    def latest_adhoc(self):
        if not self.__latest_adhoc:
            self.__latest_adhoc = self.get_latest_adhoc()
        return self.__latest_adhoc

    @latest_adhoc.setter
    def latest_adhoc(self, item):
        self.__latest_adhoc = item

    @property
    def latest_history(self):
        try:
            return self.history.all().latest()
        except AdHocRunHistory.DoesNotExist:
            return None

    def get_latest_adhoc(self):
        try:
            return self.adhoc.all().latest()
        except AdHoc.DoesNotExist:
            return None

    @property
    def history_summary(self, tasktype=None):
        if tasktype == None:
            history = self.get_run_history()
        elif tasktype == 'cmd':
            history = self.get_run_cmdhistory()
        #elif history == 'playbook':
        #    history = self.get_run_playbookhistory()

        total = len(history)
        success = len([history for history in history if history.is_success])
        failed = len([history for history in history if not history.is_success])
        return {'total': total, 'success': success, 'failed': failed}

    def get_run_history(self):
        return self.history.all()

    @property
    def latest_command(self):
        if not self.__latest_command:
            self.__latest_command = self.get_latest_command()
        return self.__latest_command

    @latest_command.setter
    def latest_command(self, item):
        self.__latest_command = item

    @property
    def latest_cmdhistory(self):
        try:
            return self.cmdhistory.all().latest()
        except CMDRunHistory.DoesNotExist:
            return None

    def get_latest_command(self):
        try:
            return self.command.all().latest()
        except Command.DoesNotExist:
            return None

    def get_run_cmdhistory(self):
        return self.cmdhistory.all()
   
    def run(self, record=True):
        if self.latest_adhoc:
            return self.latest_adhoc.run(record=record)
        elif self.latest_command:
            return self.latest_command.run(record=record)
        #elif self.latest_playbook:
        #    return self.latest_playbook.run(record=record)
        else:
            return {'error': 'No adhoc'}

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        from .tasks import run_ansible_task
        super().save(
            force_insert=force_insert,  force_update=force_update,
            using=using, update_fields=update_fields,
        )

        if self.is_periodic:
            interval = None
            crontab = None

            if self.interval:
                interval = self.interval
            elif self.crontab:
                crontab = self.crontab

            tasks = {
                self.name: {
                    "task": run_ansible_task.name,
                    "interval": interval,
                    "crontab": crontab,
                    "args": (str(self.id),),
                    "kwargs": {"callback": self.callback},
                    "enabled": True,
                }
            }
            create_or_update_celery_periodic_tasks(tasks)
        else:
            disable_celery_periodic_task(self.name)

    def delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)
        delete_celery_periodic_task(self.name)

    @property
    def schedule(self):
        try:
            return PeriodicTask.objects.get(name=self.name)
        except PeriodicTask.DoesNotExist:
            return None

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'ops_task'
        get_latest_by = 'date_created'


class AdHoc(models.Model):
    """
    task: A task reference
    _tasks: [{'name': 'task_name', 'action': {'module': '', 'args': ''}, 'other..': ''}, ]
    _options: ansible options, more see ops.ansible.runner.Options
    _hosts: ["hostname1", "hostname2"], hostname must be unique key of cmdb
    run_as_admin: if true, then need get every host admin user run it, because every host may be have different admin user, so we choise host level
    run_as: if not run as admin, it run it as a system/common user from cmdb
    _become: May be using become [sudo, su] options. {method: "sudo", user: "user", pass: "pass"]
    pattern: Even if we set _hosts, We only use that to make inventory, We also can set `patter` to run task on match hosts
    """
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    task = models.ForeignKey(Task, related_name='adhoc', on_delete=models.CASCADE)
    _tasks = models.TextField(verbose_name=_('Tasks'))
    pattern = models.CharField(max_length=64, default='{}', verbose_name=_('Pattern'))
    _options = models.CharField(max_length=1024, default='', verbose_name=_('Options'))
    _hosts = models.TextField(blank=True, verbose_name=_('Hosts'))  # ['hostname1', 'hostname2']
    run_as_admin = models.BooleanField(default=False, verbose_name=_('Run as admin'))
    run_as = models.CharField(max_length=128, default='', verbose_name=_("Run as"))
    _become = models.CharField(max_length=1024, default='', verbose_name=_("Become"))
    created_by = models.CharField(max_length=64, default='', null=True, verbose_name=_('Create by'))
    date_created = models.DateTimeField(auto_now_add=True)

    @property
    def tasks(self):
        return json.loads(self._tasks)

    @tasks.setter
    def tasks(self, item):
        if item and isinstance(item, list):
            self._tasks = json.dumps(item)
        else:
            raise SyntaxError('Tasks should be a list: {}'.format(item))

    @property
    def hosts(self):
        return json.loads(self._hosts)

    @hosts.setter
    def hosts(self, item):
        self._hosts = json.dumps(item)

    @property
    def inventory(self):
        if self.become:
            become_info = {
                'become': {
                    self.become
                }
            }
        else:
            become_info = None

        inventory = JMSInventory(
            self.hosts, run_as_admin=self.run_as_admin,
            run_as=self.run_as, become_info=become_info
        )
        return inventory

    @property
    def become(self):
        if self._become:
            return json.loads(signer.unsign(self._become))
        else:
            return {}

    def run(self, record=True):
        if record:
            return self._run_and_record()
        else:
            return self._run_only()

    def _run_and_record(self):
        history = AdHocRunHistory(adhoc=self, task=self.task)
        time_start = time.time()
        try:
            raw, summary = self._run_only()
            history.is_finished = True
            if summary.get('dark'):
                history.is_success = False
            else:
                history.is_success = True
            history.result = raw
            history.summary = summary
            return raw, summary
        except Exception as e:
            return {}, {"dark": {"all": str(e)}, "contacted": []}
        finally:
            history.date_finished = timezone.now()
            history.timedelta = time.time() - time_start
            history.save()

    def _run_only(self):
        runner = AdHocRunner(self.inventory)
        for k, v in self.options.items():
            runner.set_option(k, v)

        try:
            result = runner.run(self.tasks, self.pattern, self.task.name)
            return result.results_raw, result.results_summary
        except AnsibleError as e:
            logger.warn("Failed run adhoc {}, {}".format(self.task.name, e))
            pass

    @become.setter
    def become(self, item):
        """
        :param item:  {
            method: "sudo",
            user: "user",
            pass: "pass",
        }
        :return:
        """
        self._become = signer.sign(json.dumps(item)).decode('utf-8')

    @property
    def options(self):
        if self._options:
            _options = json.loads(self._options)
            if isinstance(_options, dict):
                return _options
        return {}

    @options.setter
    def options(self, item):
        self._options = json.dumps(item)

    @property
    def short_id(self):
        return str(self.id).split('-')[-1]

    @property
    def latest_history(self):
        try:
            return self.history.all().latest()
        except AdHocRunHistory.DoesNotExist:
            return None

    @property
    def latest_cmdhistory(self):
        try:
            return self.cmdhistory.all().latest()
        except CommandRunHistory.DoesNotExist:
            return None

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        super().save(force_insert=force_insert, force_update=force_update,
                     using=using, update_fields=update_fields)

    def __str__(self):
        return "{} of {}".format(self.task.name, self.short_id)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        fields_check = []
        for field in self.__class__._meta.fields:
            if field.name not in ['id', 'date_created']:
                fields_check.append(field)
        for field in fields_check:
            if getattr(self, field.name) != getattr(other, field.name):
                return False
        return True

    class Meta:
        db_table = "ops_adhoc"
        get_latest_by = 'date_created'


class AdHocRunHistory(models.Model):
    """
    AdHoc running history.
    """
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    task = models.ForeignKey(Task, related_name='history', on_delete=models.SET_NULL, null=True)
    adhoc = models.ForeignKey(AdHoc, related_name='history', on_delete=models.SET_NULL, null=True)
    date_start = models.DateTimeField(auto_now_add=True, verbose_name=_('Start time'))
    date_finished = models.DateTimeField(blank=True, null=True, verbose_name=_('End time'))
    timedelta = models.FloatField(default=0.0, verbose_name=_('Time'), null=True)
    is_finished = models.BooleanField(default=False, verbose_name=_('Is finished'))
    is_success = models.BooleanField(default=False, verbose_name=_('Is success'))
    _result = models.TextField(blank=True, null=True, verbose_name=_('Adhoc raw result'))
    _summary = models.TextField(blank=True, null=True, verbose_name=_('Adhoc result summary'))

    @property
    def short_id(self):
        return str(self.id).split('-')[-1]

    @property
    def result(self):
        if self._result:
            return json.loads(self._result)
        else:
            return {}

    @result.setter
    def result(self, item):
        self._result = json.dumps(item)

    @property
    def summary(self):
        if self._summary:
            return json.loads(self._summary)
        else:
            return {"ok": {}, "dark": {}}

    @summary.setter
    def summary(self, item):
        self._summary = json.dumps(item)

    @property
    def success_hosts(self):
        return self.summary.get('contacted', [])

    @property
    def failed_hosts(self):
        return self.summary.get('dark', {})

    def __str__(self):
        return self.short_id

    class Meta:
        db_table = "ops_adhoc_history"
        get_latest_by = 'date_start'

class Command(models.Model):
    """
    task: A task reference
    _tasks: ['ls', ]
    _options: ansible options, more see ops.ansible.runner.Options
    _hosts: ["hostname1", "hostname2"], hostname must be unique key of cmdb
    run_as_admin: if true, then need get every host admin user run it, because every host may be have different admin user, so we choise host level
    run_as: if not run as admin, it run it as a system/common user from cmdb
    _become: May be using become [sudo, su] options. {method: "sudo", user: "user", pass: "pass"]
    pattern: Even if we set _hosts, We only use that to make inventory, We also can set `patter` to run task on match hosts
    """
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    task = models.ForeignKey(Task, related_name='command', on_delete=models.CASCADE)
    _tasks = models.TextField(verbose_name=_('Tasks'))
    pattern = models.CharField(max_length=64, default='{}', verbose_name=_('Pattern'))
    _module = models.CharField(max_length=64, default='', null=True, verbose_name=_('Module'))
    _options = models.CharField(max_length=1024, default='', verbose_name=_('Options'))
    _hosts = models.TextField(blank=True, verbose_name=_('Hosts'))  # ['hostname1', 'hostname2']
    run_as_admin = models.BooleanField(default=False, verbose_name=_('Run as admin'))
    run_as = models.CharField(max_length=128, default='', verbose_name=_("Run as"))
    _become = models.CharField(max_length=1024, default='', verbose_name=_("Become"))
    created_by = models.CharField(max_length=64, default='', null=True, verbose_name=_('Create by'))
    date_created = models.DateTimeField(auto_now_add=True)

    #task content to execute and get result
    @property
    def tasks(self):
        return json.loads(self._tasks)

    @tasks.setter
    def tasks(self, item):
        if item and isinstance(item, str):
            self._tasks = json.dumps(item)
        else:
            raise SyntaxError('Tasks should be a list: {}'.format(item))

    #use specified module to execute ansible task, by default module is shell
    @property
    def module(self):
        return json.loads(self._module)

    @module.setter
    def module(self, item):
        self._module = json.dumps(item)

    #asset list is consist by hostname
    @property
    def hosts(self):
        return json.loads(self._hosts)

    @hosts.setter
    def hosts(self, item):
        self._hosts = json.dumps(item)

    #asset entry and user entry and task entry for ansible task  
    @property
    def inventory(self):
        # if ansible should change user to execute task, else use admin user to execute task
        if self.become:
            become_info = {
                'become': {
                    self.become
                }
            }
        else:
            become_info = None

        #jmsinventory is manage ot set ansible variables
        inventory = JMSInventory(
            self.hosts, run_as_admin=self.run_as_admin,
            run_as=self.run_as, become_info=become_info
        )
        return inventory

    #become user
    @property
    def become(self):
        if self._become:
            return json.loads(signer.unsign(self._become))
        else:
            return {}
    

    def run(self, record=True):
        """
            run_and_record(): run ansible to execute task and record result
            run_only():  just run ansible to execute task
        """
        if record:
            return self._run_and_record()
        else:
            return self._run_only()

    def _run_and_record(self):
        try:
            hid = current_task.request.id
        except AttributeError:
            hid = str(uuid.uuid4())
        history = CMDRunHistory(id=hid, command=self, task=self.task)
        time_start = time.time()
        try:
            date_start = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print("{} Start task: {}\r\n".format(date_start, self.task.name))
            raw, summary = self._run_only()
            date_end = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print("\r\n{} Task finished".format(date_end))
            history.is_finished = True
            if summary.get('dark'):
                history.is_success = False
            else:
                history.is_success = True
            history.result = raw
            history.summary = summary
            return raw, summary
        except Exception as e:
            return {}, {"dark": {"all": str(e)}, "contacted": []}
        finally:
            # f.close()
            history.date_finished = timezone.now()
            history.timedelta = time.time() - time_start
            history.save()

    def _run_only(self, file_obj=None):
        runner = CommandRunner(self.inventory)
        for k, v in self.options.items():
            runner.set_option(k, v)
        try:
            result = runner.execute(
                self.tasks, 
                self.pattern, 
                self.module,
            )
            return result.results_raw, result.results_summary
        except AnsibleError as e:
            logger.warn("Failed run adhoc {}, {}".format(self.task.name, e))
            pass

    @become.setter
    def become(self, item):
        """
        :param item:  {
            method: "sudo",
            user: "user",
            pass: "pass",
        }
        :return:
        """
        self._become = signer.sign(json.dumps(item)).decode('utf-8')

    @property
    def options(self):
        if self._options:
            _options = json.loads(self._options)
            if isinstance(_options, dict):
                return _options
        return {}

    @options.setter
    def options(self, item):
        self._options = json.dumps(item)

    @property
    def short_id(self):
        return str(self.id).split('-')[-1]

    @property
    def latest_history(self):
        try:
            return self.cmdhistory.all().latest()
        except CMDRunHistory.DoesNotExist:
            return None

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        super().save(force_insert=force_insert, force_update=force_update,
                     using=using, update_fields=update_fields)

    def __str__(self):
        return "{} of {}".format(self.task.name, self.short_id)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        fields_check = []
        for field in self.__class__._meta.fields:
            if field.name not in ['id', 'date_created']:
                fields_check.append(field)
        for field in fields_check:
            if getattr(self, field.name) != getattr(other, field.name):
                return False
        return True

    class Meta:
        db_table = "ops_command"
        get_latest_by = 'date_created'

class CMDRunHistory(models.Model):
    """
    Command running history.
    """
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    task = models.ForeignKey(Task, related_name='cmdhistory', on_delete=models.SET_NULL, null=True)
    command = models.ForeignKey(Command, related_name='history', on_delete=models.SET_NULL, null=True)
    date_start = models.DateTimeField(auto_now_add=True, verbose_name=_('Start time'))
    date_finished = models.DateTimeField(blank=True, null=True, verbose_name=_('End time'))
    timedelta = models.FloatField(default=0.0, verbose_name=_('Time'), null=True)
    is_finished = models.BooleanField(default=False, verbose_name=_('Is finished'))
    is_success = models.BooleanField(default=False, verbose_name=_('Is success'))
    _result = models.TextField(blank=True, null=True, verbose_name=_('Command raw result'))
    _summary = models.TextField(blank=True, null=True, verbose_name=_('Command result summary'))



    @property
    def short_id(self):
        return str(self.id).split('-')[-1]

    @property
    def log_path(self):
        dt = datetime.datetime.now().strftime('%Y-%m-%d')
        log_dir = os.path.join(settings.PROJECT_DIR, 'data', 'ansible', dt)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        return os.path.join(log_dir, str(self.id) + '.log')

    @property
    def result(self):
        if self._result:
            return json.loads(self._result)
        else:
            return {}

    @result.setter
    def result(self, item):
        self._result = json.dumps(item)

    @property
    def summary(self):
        if self._summary:
            return json.loads(self._summary)
        else:
            return {"ok": {}, "dark": {}}

    @summary.setter
    def summary(self, item):
        self._summary = json.dumps(item)

    @property
    def success_hosts(self):
        return self.summary.get('contacted', [])

    @property
    def failed_hosts(self):
        return self.summary.get('dark', {})

    def __str__(self):
        return self.short_id

    class Meta:
        db_table = "ops_command_history"
        get_latest_by = 'date_start'