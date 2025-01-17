# Copyright 2018-2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from flask import request
from xivo.auth_verifier import extract_token_id_from_query_or_header, Unauthorized
from wazo_auth import http
from .schemas import PasswordResetPostParameters, PasswordResetQueryParameters
from .exceptions import PasswordResetException

logger = logging.getLogger(__name__)


class PasswordReset(http.ErrorCatchingResource):

    def __init__(self, auth_client, email_service, user_service):
        self.auth_client = auth_client
        self.email_service = email_service
        self.user_service = user_service

    def get(self):
        args, errors = PasswordResetQueryParameters().load(request.args)
        if errors:
            raise PasswordResetException.from_errors(errors)

        logger.debug('resetting password for %s', args['username'] or args['email_address'])
        search_params = {k: v for k, v in args.items() if v}
        users = self.user_service.list_users(**search_params)
        if not users:
            # We do not want to leak the information if a user exists or not
            logger.debug('Failed to reset password %s', args)
        else:
            user = users[0]
            logger.debug('user: %s', user)
            email_address = args['email_address'] or self._extract_email(user)
            if email_address:
                self.email_service.send_reset_email(user['uuid'], user['username'], email_address)
            else:
                logger.debug('No confirmed email %s', args)

        return '', 204

    def post(self):
        token_id = extract_token_id_from_query_or_header()
        user_uuid = request.args.get('user_uuid')
        acl = 'auth.users.password.reset.{}.create'.format(user_uuid)

        if not self.auth_client.token.is_valid(token_id, required_acl=acl):
            raise Unauthorized(token_id)

        args, errors = PasswordResetPostParameters().load(request.get_json())
        if errors:
            raise PasswordResetException.from_errors(errors)

        if args['password'] is None:
            logger.debug('resetting password for %s', user_uuid)
            args['user_uuid'] = user_uuid
            self.user_service.delete_password(**args)
        else:
            logger.debug('changing password for %s', user_uuid)
            self.user_service.change_password(user_uuid, None, args['password'], reset=True)

        return '', 204

    def _extract_email(self, user):
        for email in user['emails']:
            if email['main'] and email['confirmed']:
                return email['address']
        for email in user['emails']:
            if email['confirmed']:
                return email['address']
