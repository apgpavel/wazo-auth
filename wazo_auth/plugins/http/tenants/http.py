# -*- coding: utf-8 -*-
# Copyright 2017 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0+

import logging

from flask import request
from wazo_auth import exceptions, http, schemas

logger = logging.getLogger(__name__)


class BaseResource(http.AuthResource):

    def __init__(self, tenant_service):
        self.tenant_service = tenant_service


class Tenant(BaseResource):

    @http.required_acl('auth.tenants.{tenant_uuid}.delete')
    def delete(self, tenant_uuid):
        logger.debug('deleting tenant %s', tenant_uuid)
        self.tenant_service.delete(tenant_uuid)
        return '', 204

    @http.required_acl('auth.tenants.{tenant_uuid}.read')
    def get(self, tenant_uuid):
        return self.tenant_service.get(tenant_uuid)


class Tenants(BaseResource):

    @http.required_acl('auth.tenants.read')
    def get(self):
        ListSchema = schemas.new_list_schema('name')
        list_params, errors = ListSchema().load(request.args)
        if errors:
            raise exceptions.InvalidListParamException(errors)

        tenants = self.tenant_service.list_(**list_params)
        total = self.tenant_service.count(filtered=False, **list_params)
        filtered = self.tenant_service.count(filtered=True, **list_params)

        response = dict(
            filtered=filtered,
            total=total,
            items=tenants,
        )

        return response, 200

    @http.required_acl('auth.tenants.create')
    def post(self):
        logger.debug('create tenant %s', request.get_json(force=True))
        args, errors = schemas.TenantRequestSchema().load(request.get_json())
        if errors:
            raise exceptions.TenantParamException.from_errors(errors)

        result = self.tenant_service.new(**args)
        return result, 200
