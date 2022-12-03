#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import fnmatch
import logging
import optparse
import galex

from . import Command
_logger = logging.getLogger(__name__)


class Populate(Command):

    def run(self, cmdargs):
        parser = galex.tools.config.parser
        group = optparse.OptionGroup(parser, "Populate Configuration")
        group.add_option("--size", dest="population_size",
                        help="Populate database with auto-generated data. Value should be the population size: small, medium or large",
                        default='small')
        group.add_option("--models",
                         dest='populate_models',
                         help="Comma separated list of model or pattern (fnmatch)")
        parser.add_option_group(group)
        opt = galex.tools.config.parse_config(cmdargs)
        populate_models = opt.populate_models and set(opt.populate_models.split(','))
        population_size = opt.population_size
        with galex.api.Environment.manage():
            dbname = galex.tools.config['db_name']
            registry = galex.registry(dbname)
            with registry.cursor() as cr:
                env = galex.api.Environment(cr, galex.SUPERUSER_ID, {})
                self.populate(env, population_size, populate_models)


    @classmethod
    def populate(cls, env, size, model_patterns=False):
        registry = env.registry
        populated_models = None
        try:
            registry.populated_models = {}  # todo master, initialize with already populated models
            ordered_models = cls._get_ordered_models(env, model_patterns)

            _logger.log(25, 'Populating database')
            for model in ordered_models:
                _logger.info('Populating database for model %s', model._name)
                t0 = time.time()
                registry.populated_models[model._name] = model._populate(size).ids
                # todo indicate somewhere that model is populated
                env.cr.commit()
                model_time = time.time() - t0
                if model_time > 1:
                    _logger.info('Populated database for model %s in %ss', model._name, model_time)
        except:
            _logger.exception('Something went wrong populating database')
        finally:
            populated_models = registry.populated_models
            del registry.populated_models

        return populated_models

    @classmethod
    def _get_ordered_models(cls, env, model_patterns=False):
        _logger.info('Computing model order')
        processed = set()
        ordered_models = []
        visited = set()
        def add_model(model):
            if model not in processed:
                if model in visited:
                    raise ValueError('Cyclic dependency detected for %s' % model)
                visited.add(model)
                for dep in model._populate_dependencies:
                    add_model(env[dep])
                ordered_models.append(model)
                processed.add(model)
        for model in env.values():
            ir_model = env['ir.model'].search([('model', '=', model._name)])
            if model_patterns and not any(fnmatch.fnmatch(model._name, match) for match in model_patterns):
                continue
            if model._transient or model._abstract:
                continue
            if not model_patterns and all(module.startswith('test_') for module in ir_model.modules.split(',')):
                continue
            add_model(model)

        return ordered_models
