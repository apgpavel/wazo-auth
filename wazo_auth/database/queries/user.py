# -*- coding: utf-8 -*-
# Copyright 2017-2018 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0+

from collections import OrderedDict
from sqlalchemy import and_, exc, text
from .base import BaseDAO, PaginatorMixin
from . import filters
from ..models import (
    Email,
    Group,
    Policy,
    User,
    UserEmail,
    UserGroup,
    UserPolicy,
)
from ... import exceptions


class UserDAO(filters.FilterMixin, PaginatorMixin, BaseDAO):

    constraint_to_column_map = {
        'auth_user_pkey': 'uuid',
        'auth_user_username_key': 'username',
        'auth_email_address_key': 'email_address',
    }
    search_filter = filters.user_search_filter
    strict_filter = filters.user_strict_filter
    column_map = {'username': User.username}

    def add_policy(self, user_uuid, policy_uuid):
        user_policy = UserPolicy(user_uuid=user_uuid, policy_uuid=policy_uuid)
        with self.new_session() as s:
            s.add(user_policy)
            try:
                s.commit()
            except exc.IntegrityError as e:
                if e.orig.pgcode == self._UNIQUE_CONSTRAINT_CODE:
                    # This association already exists.
                    s.rollback()
                    return
                if e.orig.pgcode == self._FKEY_CONSTRAINT_CODE:
                    constraint = e.orig.diag.constraint_name
                    if constraint == 'auth_user_policy_user_uuid_fkey':
                        raise exceptions.UnknownUserException(user_uuid)
                    elif constraint == 'auth_user_policy_policy_uuid_fkey':
                        raise exceptions.UnknownPolicyException(policy_uuid)
                raise

    def change_password(self, user_uuid, salt, hash_):
        filter_ = User.uuid == str(user_uuid)
        values = {
            'password_salt': salt,
            'password_hash': hash_,
        }

        with self.new_session() as s:
            s.query(User).filter(filter_).update(values)

    def exists(self, user_uuid, tenant_uuids=None):
        kwargs = {'uuid': user_uuid}
        if tenant_uuids is not None:
            kwargs['tenant_uuids'] = tenant_uuids
        return self.count(**kwargs) > 0

    def remove_policy(self, user_uuid, policy_uuid):
        filter_ = and_(
            UserPolicy.user_uuid == user_uuid,
            UserPolicy.policy_uuid == policy_uuid,
        )

        with self.new_session() as s:
            return s.query(UserPolicy).filter(filter_).delete()

    def count(self, **kwargs):
        filter_ = text('true')

        tenant_uuid = kwargs.get('tenant_uuid')
        if tenant_uuid:
            filter_ = User.tenant_uuid == tenant_uuid

        tenant_uuids = kwargs.get('tenant_uuids')
        if tenant_uuids:
            filter_ = User.tenant_uuid.in_(tenant_uuids)

        filtered = kwargs.get('filtered')
        if filtered is not False:
            strict_filter = self.new_strict_filter(**kwargs)
            search_filter = self.new_search_filter(**kwargs)
            filter_ = and_(filter_, strict_filter, search_filter)

        with self.new_session() as s:
            return s.query(
                User.uuid,
            ).outerjoin(
                UserEmail, UserEmail.user_uuid == User.uuid,
            ).outerjoin(
                Email, Email.uuid == UserEmail.email_uuid
            ).filter(filter_).count()

    def count_groups(self, user_uuid, **kwargs):
        filtered = kwargs.get('filtered')
        if filtered is not False:
            strict_filter = filters.group_strict_filter.new_filter(**kwargs)
            search_filter = filters.group_search_filter.new_filter(**kwargs)
            filter_ = and_(strict_filter, search_filter)
        else:
            filter_ = text('true')

        filter_ = and_(filter_, UserGroup.user_uuid == str(user_uuid))

        with self.new_session() as s:
            return s.query(Group).join(UserGroup).filter(filter_).count()

    def count_policies(self, user_uuid, **kwargs):
        filtered = kwargs.get('filtered')
        if filtered is not False:
            strict_filter = filters.policy_strict_filter.new_filter(**kwargs)
            search_filter = filters.policy_search_filter.new_filter(**kwargs)
            filter_ = and_(strict_filter, search_filter)
        else:
            filter_ = text('true')

        filter_ = and_(filter_, UserPolicy.user_uuid == user_uuid)

        with self.new_session() as s:
            return s.query(Policy).join(
                UserPolicy, UserPolicy.policy_uuid == Policy.uuid,
            ).filter(filter_).count()

    def create(self, username, **kwargs):
        user_args = {
            'username': username,
            'firstname': kwargs.get('firstname'),
            'lastname': kwargs.get('lastname'),
            'password_hash': kwargs.get('hash_'),
            'password_salt': kwargs.get('salt'),
            'enabled': kwargs.get('enabled'),
            'tenant_uuid': kwargs['tenant_uuid'],
        }
        uuid = kwargs.get('uuid')
        if uuid:
            user_args['uuid'] = str(uuid)

        email_confirmed = kwargs.get('email_confirmed', False)
        email_address = kwargs.get('email_address', None)
        with self.new_session() as s:
            try:
                if email_address:
                    email_args = {'address': email_address, 'confirmed': email_confirmed}
                    email = Email(**email_args)
                    s.add(email)

                user = User(**user_args)
                s.add(user)
                s.flush()
                if email_address:
                    user_email = UserEmail(
                        user_uuid=user.uuid,
                        email_uuid=email.uuid,
                        main=True,
                    )
                    s.add(user_email)
                    s.commit()
            except exc.IntegrityError as e:
                if e.orig.pgcode == self._UNIQUE_CONSTRAINT_CODE:
                    column = self.constraint_to_column_map.get(e.orig.diag.constraint_name)
                    value = locals().get(column)
                    if column:
                        raise exceptions.ConflictException('users', column, value)
                raise

            if email_address:
                email = {
                    'uuid': email.uuid,
                    'address': email_address,
                    'confirmed': email_confirmed,
                    'main': True,
                }
                emails = [email]
            else:
                emails = []

            return {
                'uuid': user.uuid,
                'username': username,
                'firstname': user.firstname,
                'lastname': user.lastname,
                'emails': emails,
                'enabled': user.enabled,
                'tenant_uuid': user.tenant_uuid,
            }

    def delete(self, user_uuid):
        filter_ = User.uuid == user_uuid

        with self.new_session() as s:
            # TODO find a way to delete all linked voicemails without doing separate queries
            rows = s.query(UserEmail.email_uuid).filter(UserEmail.user_uuid == user_uuid).all()
            email_ids = [row.email_uuid for row in rows]
            if email_ids:
                s.query(Email).filter(Email.uuid.in_(email_ids)).delete(synchronize_session=False)
            nb_deleted = s.query(User).filter(filter_).delete(synchronize_session=False)

        if not nb_deleted:
            raise exceptions.UnknownUserException(user_uuid)

    def get_credentials(self, username):
        filter_ = and_(
            self.new_strict_filter(username=username),
            User.enabled.is_(True),
        )

        with self.new_session() as s:
            query = s.query(
                User.password_salt,
                User.password_hash,
            ).filter(filter_)

            for row in query.all():
                return row.password_hash, row.password_salt

            raise exceptions.UnknownUsernameException(username)

    def get_emails(self, user_uuid):
        filter_ = UserEmail.user_uuid == str(user_uuid)
        result = []

        with self.new_session() as s:
            query = s.query(
                Email.uuid,
                Email.address,
                Email.confirmed,
                UserEmail.main,
            ).outerjoin(UserEmail).filter(filter_)

            for row in query.all():
                result.append(
                    {
                        'uuid': row.uuid,
                        'address': row.address,
                        'main': row.main,
                        'confirmed': row.confirmed,
                    }
                )

        if not result and not self.exists(user_uuid):
            raise exceptions.UnknownUserException(user_uuid)

        return result

    def list_(self, **kwargs):
        users = OrderedDict()
        search_filter = self.new_search_filter(**kwargs)
        strict_filter = self.new_strict_filter(**kwargs)
        filter_ = and_(strict_filter, search_filter)

        with self.new_session() as s:
            query = s.query(
                User.uuid,
                User.username,
                User.firstname,
                User.lastname,
                User.enabled,
                User.tenant_uuid,
                UserEmail.main,
                Email.uuid,
                Email.address,
                Email.confirmed,
            ).outerjoin(
                UserEmail, User.uuid == UserEmail.user_uuid,
            ).outerjoin(
                Email, Email.uuid == UserEmail.email_uuid,
            ).outerjoin(UserGroup).filter(filter_)
            query = self._paginator.update_query(query, **kwargs)
            rows = query.all()

            for row in rows:
                (
                    user_uuid,
                    username,
                    firstname,
                    lastname,
                    enabled,
                    tenant_uuid,
                    main_email,
                    email_uuid,
                    address,
                    confirmed,
                ) = row

                if user_uuid not in users:
                    users[user_uuid] = {
                        'username': username,
                        'uuid': user_uuid,
                        'enabled': enabled,
                        'emails': [],
                        'firstname': firstname,
                        'lastname': lastname,
                        'tenant_uuid': tenant_uuid,
                    }

                if address:
                    email = {
                        'uuid': email_uuid,
                        'address': address,
                        'main': main_email,
                        'confirmed': confirmed,
                    }
                    if email not in users[user_uuid]['emails']:
                        users[user_uuid]['emails'].append(email)

        return users.values()

    def update(self, user_uuid, **kwargs):
        filter_ = User.uuid == str(user_uuid)

        with self.new_session() as s:
            s.query(User).filter(filter_).update(kwargs)

    def update_emails(self, user_uuid, emails):
        existing_addresses = self._emails_to_dict(self.get_emails(user_uuid))
        emails_as_dict = self._emails_to_dict(emails)
        updated_emails = self._merge_existing_emails(emails_as_dict, existing_addresses)

        with self.new_session() as s:
            self._delete_all_emails(s, user_uuid)

            for email in updated_emails.itervalues():
                self._add_user_email(s, user_uuid, email)

        return emails

    def _add_user_email(self, s, user_uuid, args):
        args.setdefault('confirmed', False)
        email = Email(address=args['address'])
        email.confirmed = args['confirmed']
        uuid = args.get('uuid')
        if uuid:
            email.uuid = uuid
        s.add(email)
        s.flush()
        s.add(UserEmail(
            email_uuid=email.uuid,
            user_uuid=user_uuid,
            main=args['main'],
        ))
        s.flush()
        args['uuid'] = email.uuid

    def _delete_all_emails(self, s, user_uuid):
        filter_ = UserEmail.user_uuid == str(user_uuid)

        query = s.query(UserEmail.email_uuid).filter(filter_)
        email_uuids = [row.email_uuid for row in query.all()]
        if email_uuids:
            s.query(Email).filter(Email.uuid.in_(email_uuids)).delete(synchronize_session=False)

    @staticmethod
    def _emails_to_dict(emails):
        result = {}
        for email in emails:
            result[email['address']] = email
        return result

    @staticmethod
    def _merge_existing_emails(new, old):
        for address, email in new.iteritems():
            if address not in old:
                continue

            email['uuid'] = old[address]['uuid']
            if email.get('confirmed') is None:
                email['confirmed'] = old[address]['confirmed']

        return new
