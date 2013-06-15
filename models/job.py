# No shebang line, this module is meant to be imported
#
# Copyright 2013 Oliver Palmer
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from datetime import datetime
from UserDict import UserDict

try:
    import pwd
except ImportError:
    pwd = None

try:
    import json
except ImportError:
    import simplejson as json

try:
    property.setter
except AttributeError:
    from pyfarm.backports import _property as property

from sqlalchemy import event
from sqlalchemy.orm import validates

from pyfarm.flaskapp import db
from pyfarm.config.enum import WorkState
from pyfarm.models.constants import (
    DBDATA, TABLE_JOB, TABLE_JOB_TAGS, TABLE_JOB_SOFTWARE
)
from pyfarm.models.mixins import (
    RandIdMixin, StateValidationMixin, StateChangedMixin)


class JobTags(db.Model):
    __tablename__ = TABLE_JOB_TAGS
    _jobid = db.Column(db.Integer, db.ForeignKey("%s.id" % TABLE_JOB),
                         primary_key=True)
    tag = db.Column(db.String)


class JobSoftware(db.Model):
    __tablename__ = TABLE_JOB_SOFTWARE
    _jobid = db.Column(db.Integer, db.ForeignKey("%s.id" % TABLE_JOB),
                         primary_key=True)
    software = db.Column(db.String)


class Job(db.Model, RandIdMixin, StateValidationMixin, StateChangedMixin):
    """Defines task which a child of a :class:`.Job`"""
    __tablename__ = TABLE_JOB
    STATE_ENUM = WorkState()
    STATE_DEFAULT = STATE_ENUM.QUEUED

    state = db.Column(db.Integer, default=STATE_DEFAULT)
    cmd = db.Column(db.String)
    priority = db.Column(db.Integer, default=DBDATA.get("job.priority"))
    user = db.Column(db.String(DBDATA.get("job.max_username_length")))
    notes = db.Column(db.Text, default="")
    time_submitted = db.Column(db.DateTime, default=datetime.now)
    time_started = db.Column(db.DateTime)
    time_finished = db.Column(db.DateTime)
    start = db.Column(db.Float, nullable=False)
    end = db.Column(db.Float, nullable=False)
    by = db.Column(db.Float, default=1)

    # underlying storage for properties
    _environ = db.Column(db.Text)
    _args = db.Column(db.Text)
    _data = db.Column(db.Text)

    # relationships
    tasks = db.relationship("Task", backref="job", lazy="dynamic")
    tasks_done = db.relationship("Task", lazy="dynamic",
        primaryjoin="(Task.state == %s) & "
                    "(Task._jobid == Job.id)" % STATE_ENUM.DONE)
    tasks_failed = db.relationship("Task", lazy="dynamic",
        primaryjoin="(Task.state == %s) & "
                    "(Task._jobid == Job.id)" % STATE_ENUM.FAILED)
    tasks_queued = db.relationship("Task", lazy="dynamic",
        primaryjoin="(Task.state == %s) & "
                    "(Task._jobid == Job.id)" % STATE_ENUM.QUEUED)
    tags = db.relationship("JobTags", backref="job", lazy="dynamic")
    software = db.relationship("JobSoftware", backref="job", lazy="dynamic")

    @property
    def environ(self):
        if not self._environ:
            return os.environ.copy()

        value = json.loads(self._environ)
        assert isinstance(value, dict), "expected a dictionary from _environ"
        return value

    @environ.setter
    def environ(self, value):
        if isinstance(value, dict):
            value = json.dumps(value)
        elif isinstance(value, UserDict):
            value = json.dumps(value.data)
        else:
            raise TypeError("expected a dict or UserDict object for `environ`")

        self._environ = value

    @property
    def data(self):
        return json.loads(self._data)

    @data.setter
    def data(self, value):
        self._data = json.dumps(value)

    @property
    def args(self):
        return json.loads(self._args)

    @args.setter
    def args(self, value):
        assert isinstance(value, list), "expected a list for `args`"
        self._args = json.dumps(value)

    @validates("environ")
    def validation_environ(self, key, value):
        if not isinstance(value, (dict, UserDict, basestring)):
            raise TypeError("expected a dictionary or string for %s" % key)

        return value

    @validates("user")
    def validate_user(self, key, value):
        max_length = DBDATA.get("job.max_username_length")
        if len(value) > max_length:
            msg = "max user name length is %s" % max_length
            raise ValueError(msg)

        return value

    @validates("_environ")
    def validate_json(self, key, value):
        try:
            json.dumps(value)
        except Exception, e:
            raise ValueError("failed to dump `%s` to json: %s" % (key, e))

        return value

    @validates("user")
    def validate_user(self, key, value):
        if pwd is not None:
            try:
                pwd.getpwnam(value)
            except:
                raise ValueError("no such user `%s` could be found" % value)

        return value

event.listen(Job.state, "set", Job.stateChangedEvent)