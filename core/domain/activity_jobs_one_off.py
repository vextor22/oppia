# coding: utf-8
#
# Copyright 2017 The Oppia Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""One-off jobs for activities."""

from __future__ import absolute_import  # pylint: disable=import-only-modules
from __future__ import unicode_literals  # pylint: disable=import-only-modules

from core import jobs
from core.domain import collection_services
from core.domain import exp_fetchers
from core.domain import exp_services
from core.domain import rights_domain
from core.domain import search_services
from core.domain import topic_domain
from core.domain import user_services
from core.platform import models
import python_utils

(
    collection_models, exp_models, question_models,
    skill_models, story_models, topic_models,
    subtopic_models
) = models.Registry.import_models([
    models.NAMES.collection, models.NAMES.exploration, models.NAMES.question,
    models.NAMES.skill, models.NAMES.story, models.NAMES.topic,
    models.NAMES.subtopic
])
transaction_services = models.Registry.import_transaction_services()


class ActivityContributorsSummaryOneOffJob(jobs.BaseMapReduceOneOffJobManager):
    """One-off job that computes the number of commits done by contributors for
    each collection and exploration.
    """

    @classmethod
    def entity_classes_to_map_over(cls):
        return [collection_models.CollectionModel, exp_models.ExplorationModel]

    @staticmethod
    def map(model):
        if model.deleted:
            return

        if isinstance(model, collection_models.CollectionModel):
            summary = collection_services.get_collection_summary_by_id(model.id)
            summary.contributors_summary = (
                collection_services.compute_collection_contributors_summary(
                    model.id))
            summary.contributor_ids = list(summary.contributors_summary)
            collection_services.save_collection_summary(summary)
        else:
            summary = exp_fetchers.get_exploration_summary_by_id(model.id)
            summary.contributors_summary = (
                exp_services.compute_exploration_contributors_summary(model.id))
            summary.contributor_ids = list(summary.contributors_summary)
            exp_services.save_exploration_summary(summary)
        yield ('SUCCESS', model.id)

    @staticmethod
    def reduce(key, values):
        yield (key, len(values))


class AuditContributorsOneOffJob(jobs.BaseMapReduceOneOffJobManager):
    """Audit job that compares the contents of contributor_ids and
    contributors_summary.
    """

    @classmethod
    def entity_classes_to_map_over(cls):
        return [exp_models.ExpSummaryModel,
                collection_models.CollectionSummaryModel]

    @staticmethod
    def map(model):
        ids_set = set(model.contributor_ids)
        summary_set = set(model.contributors_summary)
        if len(ids_set) != len(model.contributor_ids):
            # When the contributor_ids contain duplicate ids.
            yield (
                'DUPLICATE_IDS',
                (model.id, model.contributor_ids, model.contributors_summary)
            )
        if ids_set - summary_set:
            # When the contributor_ids contain id that is not in
            # contributors_summary.
            yield (
                'MISSING_IN_SUMMARY',
                (model.id, model.contributor_ids, model.contributors_summary)
            )
        if summary_set - ids_set:
            # When the contributors_summary contains id that is not in
            # contributor_ids.
            yield (
                'MISSING_IN_IDS',
                (model.id, model.contributor_ids, model.contributors_summary)
            )
        yield ('SUCCESS', model.id)

    @staticmethod
    def reduce(key, values):
        if key == 'SUCCESS':
            yield (key, len(values))
        else:
            yield (key, values)


class IndexAllActivitiesJobManager(jobs.BaseMapReduceOneOffJobManager):
    """Job that indexes all explorations and collections and compute their
    ranks.
    """

    @classmethod
    def entity_classes_to_map_over(cls):
        return [exp_models.ExpSummaryModel,
                collection_models.CollectionSummaryModel]

    @staticmethod
    def map(item):
        if not item.deleted:
            if isinstance(item, exp_models.ExpSummaryModel):
                search_services.index_exploration_summaries([item])
            else:
                search_services.index_collection_summaries([item])

    @staticmethod
    def reduce(key, values):
        pass


class AddContentUserIdsContentJob(jobs.BaseMapReduceOneOffJobManager):
    """For every snapshot content of a rights model, merge the data from all
    the user id fields in content together and put them in the
    content_user_ids field of an appropriate RightsSnapshotMetadataModel.
    """

    @staticmethod
    def _add_collection_user_ids(snapshot_content_model):
        """Merge the user ids from the snapshot content and put them in
        the snapshot metadata content_user_ids field.
        """
        content_dict = (
            collection_models.CollectionRightsModel.convert_to_valid_dict(
                snapshot_content_model.content))
        reconstituted_rights_model = (
            collection_models.CollectionRightsModel(**content_dict))
        snapshot_metadata_model = (
            collection_models.CollectionRightsSnapshotMetadataModel.get_by_id(
                snapshot_content_model.id))
        snapshot_metadata_model.content_user_ids = list(sorted(
            set(reconstituted_rights_model.owner_ids) |
            set(reconstituted_rights_model.editor_ids) |
            set(reconstituted_rights_model.voice_artist_ids) |
            set(reconstituted_rights_model.viewer_ids)))
        snapshot_metadata_model.put(update_last_updated_time=False)

    @staticmethod
    def _add_exploration_user_ids(snapshot_content_model):
        """Merge the user ids from the snapshot content and put them in
        the snapshot metadata content_user_ids field.
        """
        content_dict = (
            exp_models.ExplorationRightsModel.convert_to_valid_dict(
                snapshot_content_model.content))
        reconstituted_rights_model = (
            exp_models.ExplorationRightsModel(**content_dict))
        snapshot_metadata_model = (
            exp_models.ExplorationRightsSnapshotMetadataModel.get_by_id(
                snapshot_content_model.id))
        snapshot_metadata_model.content_user_ids = list(sorted(
            set(reconstituted_rights_model.owner_ids) |
            set(reconstituted_rights_model.editor_ids) |
            set(reconstituted_rights_model.voice_artist_ids) |
            set(reconstituted_rights_model.viewer_ids)))
        snapshot_metadata_model.put(update_last_updated_time=False)

    @staticmethod
    def _add_topic_user_ids(snapshot_content_model):
        """Merge the user ids from the snapshot content and put them in
        the snapshot metadata content_user_ids field.
        """
        reconstituted_rights_model = topic_models.TopicRightsModel(
            **snapshot_content_model.content)
        snapshot_metadata_model = (
            topic_models.TopicRightsSnapshotMetadataModel.get_by_id(
                snapshot_content_model.id))
        snapshot_metadata_model.content_user_ids = list(sorted(set(
            reconstituted_rights_model.manager_ids)))
        snapshot_metadata_model.put(update_last_updated_time=False)

    @classmethod
    def enqueue(cls, job_id, additional_job_params=None):
        # We can raise the number of shards for this job, since it goes only
        # over three types of entity class.
        super(AddContentUserIdsContentJob, cls).enqueue(
            job_id, shard_count=64)

    @classmethod
    def entity_classes_to_map_over(cls):
        """Return a list of datastore class references to map over."""
        return [collection_models.CollectionRightsSnapshotContentModel,
                exp_models.ExplorationRightsSnapshotContentModel,
                topic_models.TopicRightsSnapshotContentModel]

    @staticmethod
    def map(rights_snapshot_model):
        """Implements the map function for this job."""
        class_name = rights_snapshot_model.__class__.__name__
        if isinstance(
                rights_snapshot_model,
                collection_models.CollectionRightsSnapshotContentModel):
            AddContentUserIdsContentJob._add_collection_user_ids(
                rights_snapshot_model)
        elif isinstance(
                rights_snapshot_model,
                exp_models.ExplorationRightsSnapshotContentModel):
            AddContentUserIdsContentJob._add_exploration_user_ids(
                rights_snapshot_model)
        elif isinstance(
                rights_snapshot_model,
                topic_models.TopicRightsSnapshotContentModel):
            AddContentUserIdsContentJob._add_topic_user_ids(
                rights_snapshot_model)
        yield ('SUCCESS-%s' % class_name, rights_snapshot_model.id)

    @staticmethod
    def reduce(key, ids):
        """Implements the reduce function for this job."""
        yield (key, len(ids))


class AddCommitCmdsUserIdsMetadataJob(jobs.BaseMapReduceOneOffJobManager):
    """For every snapshot metadata of a rights model, merge the data from all
    the user id fields in commit_cmds together and put them in the
    commit_cmds_user_ids field of an appropriate RightsSnapshotMetadataModel.
    """

    @staticmethod
    def _migrate_user_id(snapshot_model):
        """Fix the assignee_id in commit_cmds in snapshot metadata and commit
        log models. This is only run on models that have commit_cmds of length
        two. This is stuff that was missed in the user ID migration.

        Args:
            snapshot_model: BaseSnapshotMetadataModel. Snapshot metadata model
                to migrate.

        Returns:
            (str, str). Result info, first part is result message, second is
            additional info like IDs.
        """
        # Only commit_cmds of length 2 are processed by this method.
        assert len(snapshot_model.commit_cmds) == 2
        new_user_ids = [None, None]
        for i, commit_cmd in enumerate(snapshot_model.commit_cmds):
            assignee_id = commit_cmd['assignee_id']
            if (
                    commit_cmd['cmd'] == rights_domain.CMD_CHANGE_ROLE and
                    not user_services.is_user_id_valid(assignee_id)
            ):
                user_settings = user_services.get_user_settings_by_gae_id(
                    assignee_id)
                if user_settings is None:
                    return (
                        'MIGRATION_FAILURE', (snapshot_model.id, assignee_id))

                new_user_ids[i] = user_settings.user_id

        # This loop is used for setting the actual commit_cmds and is separate
        # because if the second commit results in MIGRATION_FAILURE we do not
        # want to set the first one either. We want to either set the correct
        # user IDs in both commits or we don't want to set it at all.
        for i in python_utils.RANGE(len(snapshot_model.commit_cmds)):
            if new_user_ids[i] is not None:
                snapshot_model.commit_cmds[i]['assignee_id'] = new_user_ids[i]

        commit_log_model = (
            exp_models.ExplorationCommitLogEntryModel.get_by_id(
                'rights-%s-%s' % (
                    snapshot_model.get_unversioned_instance_id(),
                    snapshot_model.get_version_string())
            )
        )
        if commit_log_model is None:
            snapshot_model.put(update_last_updated_time=False)
            return (
                'MIGRATION_SUCCESS_MISSING_COMMIT_LOG',
                snapshot_model.id
            )

        commit_log_model.commit_cmds = snapshot_model.commit_cmds

        def _put_both_models():
            """Put both models into the datastore together."""
            snapshot_model.put(update_last_updated_time=False)
            commit_log_model.put(update_last_updated_time=False)

        transaction_services.run_in_transaction(_put_both_models)
        return ('MIGRATION_SUCCESS', snapshot_model.id)

    @staticmethod
    def _add_col_and_exp_user_ids(snapshot_model):
        """Merge the user ids from the commit_cmds and put them in the
        commit_cmds_user_ids field.

        Args:
            snapshot_model: BaseSnapshotMetadataModel. Snapshot metadata model
                to add user IDs to.
        """
        commit_cmds_user_ids = set()
        for commit_cmd in snapshot_model.commit_cmds:
            if commit_cmd['cmd'] == rights_domain.CMD_CHANGE_ROLE:
                commit_cmds_user_ids.add(commit_cmd['assignee_id'])
        snapshot_model.commit_cmds_user_ids = list(
            sorted(commit_cmds_user_ids))
        snapshot_model.put(update_last_updated_time=False)

    @staticmethod
    def _add_topic_user_ids(snapshot_model):
        """Merge the user ids from the commit_cmds and put them in the
        commit_cmds_user_ids field.

        Args:
            snapshot_model: BaseSnapshotMetadataModel. Snapshot metadata model
                to add user IDs to.
        """
        commit_cmds_user_ids = set()
        for commit_cmd in snapshot_model.commit_cmds:
            if commit_cmd['cmd'] == topic_domain.CMD_CHANGE_ROLE:
                commit_cmds_user_ids.add(commit_cmd['assignee_id'])
            elif commit_cmd['cmd'] == topic_domain.CMD_REMOVE_MANAGER_ROLE:
                commit_cmds_user_ids.add(commit_cmd['removed_user_id'])
        snapshot_model.commit_cmds_user_ids = list(
            sorted(commit_cmds_user_ids))
        snapshot_model.put(update_last_updated_time=False)

    @classmethod
    def enqueue(cls, job_id, additional_job_params=None):
        # We can raise the number of shards for this job, since it goes only
        # over three types of entity class.
        super(AddCommitCmdsUserIdsMetadataJob, cls).enqueue(
            job_id, shard_count=64)

    @classmethod
    def entity_classes_to_map_over(cls):
        """Return a list of datastore class references to map over."""
        return [collection_models.CollectionRightsSnapshotMetadataModel,
                exp_models.ExplorationRightsSnapshotMetadataModel,
                topic_models.TopicRightsSnapshotMetadataModel]

    @staticmethod
    def map(snapshot_model):
        """Implements the map function for this job."""
        class_name = snapshot_model.__class__.__name__
        if isinstance(
                snapshot_model,
                collection_models.CollectionRightsSnapshotMetadataModel):
            AddCommitCmdsUserIdsMetadataJob._add_col_and_exp_user_ids(
                snapshot_model)
        elif isinstance(
                snapshot_model,
                exp_models.ExplorationRightsSnapshotMetadataModel):
            # From audit job and analysis of the user ID migration we know that
            # only commit_cmds of length 2 can have a wrong user ID.
            if len(snapshot_model.commit_cmds) == 2:
                result = AddCommitCmdsUserIdsMetadataJob._migrate_user_id(
                    snapshot_model)
                yield result
            AddCommitCmdsUserIdsMetadataJob._add_col_and_exp_user_ids(
                snapshot_model)
        elif isinstance(
                snapshot_model,
                topic_models.TopicRightsSnapshotMetadataModel):
            AddCommitCmdsUserIdsMetadataJob._add_topic_user_ids(snapshot_model)
        yield ('SUCCESS-%s' % class_name, snapshot_model.id)

    @staticmethod
    def reduce(key, ids):
        """Implements the reduce function for this job."""
        if key.startswith('SUCCESS') or key == 'MIGRATION_SUCCESS':
            yield (key, len(ids))
        else:
            yield (key, ids)


class AuditSnapshotMetadataModelsJob(jobs.BaseMapReduceOneOffJobManager):
    """Job that audits commit_cmds field of the snapshot metadata models. We log
    the length of the commit_cmd, the possible 'cmd' values, and all the other
    keys.
    """

    @classmethod
    def enqueue(cls, job_id, additional_job_params=None):
        # We can raise the number of shards for this job, since it goes only
        # over three types of entity class.
        super(AuditSnapshotMetadataModelsJob, cls).enqueue(
            job_id, shard_count=64)

    @classmethod
    def entity_classes_to_map_over(cls):
        """Return a list of datastore class references to map over."""
        return [collection_models.CollectionRightsSnapshotMetadataModel,
                exp_models.ExplorationRightsSnapshotMetadataModel,
                topic_models.TopicRightsSnapshotMetadataModel]

    @staticmethod
    def map(snapshot_model):
        """Implements the map function for this job."""
        if isinstance(
                snapshot_model,
                collection_models.CollectionRightsSnapshotMetadataModel):
            model_type_name = 'collection'
        elif isinstance(
                snapshot_model,
                exp_models.ExplorationRightsSnapshotMetadataModel):
            model_type_name = 'exploration'
        elif isinstance(
                snapshot_model,
                topic_models.TopicRightsSnapshotMetadataModel):
            model_type_name = 'topic'

        if snapshot_model.deleted:
            yield ('%s-deleted' % model_type_name, 1)
            return

        first_commit_cmd = None
        for commit_cmd in snapshot_model.commit_cmds:
            if 'cmd' in commit_cmd:
                cmd_name = commit_cmd['cmd']
                yield ('%s-cmd-%s' % (model_type_name, cmd_name), 1)
            else:
                cmd_name = 'missing_cmd'
                yield ('%s-missing-cmd' % model_type_name, 1)

            if first_commit_cmd is None:
                first_commit_cmd = cmd_name

            for field_key in commit_cmd.keys():
                if field_key != 'cmd':
                    yield (
                        '%s-%s-field-%s' % (
                            model_type_name, cmd_name, field_key
                        ),
                        1
                    )

        if first_commit_cmd is not None:
            yield (
                '%s-%s-length-%s' % (
                    model_type_name,
                    first_commit_cmd,
                    len(snapshot_model.commit_cmds)),
                1
            )
        else:
            yield (
                '%s-length-%s' % (
                    model_type_name, len(snapshot_model.commit_cmds)),
                1
            )

    @staticmethod
    def reduce(key, values):
        """Implements the reduce function for this job."""
        yield (key, len(values))


class ValidateSnapshotMetadataModelsJob(jobs.BaseMapReduceOneOffJobManager):
    """Job that validates whether each SnapshotMetadata model has a
    corresponding CommitLog model pair and the corresponding parent model.
    """

    FAILURE_PREFIX = 'VALIDATION FAILURE'
    SNAPSHOT_METADATA_MODELS = [
        collection_models.CollectionSnapshotMetadataModel,
        collection_models.CollectionRightsSnapshotMetadataModel,
        exp_models.ExplorationSnapshotMetadataModel,
        exp_models.ExplorationRightsSnapshotMetadataModel,
        question_models.QuestionSnapshotMetadataModel,
        skill_models.SkillSnapshotMetadataModel,
        story_models.StorySnapshotMetadataModel,
        topic_models.TopicSnapshotMetadataModel,
        subtopic_models.SubtopicPageSnapshotMetadataModel,
        topic_models.TopicRightsSnapshotMetadataModel
    ]
    MODEL_NAMES_TO_PROPERTIES = {
        'CollectionSnapshotMetadataModel': {
            'parent_model_class': collection_models.CollectionModel,
            'commit_log_model_class': (
                collection_models.CollectionCommitLogEntryModel),
            'id_string_format': 'collection-%s-%s'
        },
        'ExplorationSnapshotMetadataModel': {
            'parent_model_class': exp_models.ExplorationModel,
            'commit_log_model_class': exp_models.ExplorationCommitLogEntryModel,
            'id_string_format': 'exploration-%s-%s'
        },
        'QuestionSnapshotMetadataModel': {
            'parent_model_class': question_models.QuestionModel,
            'commit_log_model_class': (
                question_models.QuestionCommitLogEntryModel),
            'id_string_format': 'question-%s-%s'
        },
        'SkillSnapshotMetadataModel': {
            'parent_model_class': skill_models.SkillModel,
            'commit_log_model_class': skill_models.SkillCommitLogEntryModel,
            'id_string_format': 'skill-%s-%s'
        },
        'StorySnapshotMetadataModel': {
            'parent_model_class': story_models.StoryModel,
            'commit_log_model_class': story_models.StoryCommitLogEntryModel,
            'id_string_format': 'story-%s-%s'
        },
        'TopicSnapshotMetadataModel': {
            'parent_model_class': topic_models.TopicModel,
            'commit_log_model_class': topic_models.TopicCommitLogEntryModel,
            'id_string_format': 'topic-%s-%s'
        },
        'SubtopicPageSnapshotMetadataModel': {
            'parent_model_class': subtopic_models.SubtopicPageModel,
            'commit_log_model_class': (
                subtopic_models.SubtopicPageCommitLogEntryModel),
            'id_string_format': 'subtopicpage-%s-%s'
        },
        'TopicRightsSnapshotMetadataModel': {
            'parent_model_class': topic_models.TopicRightsModel,
            'commit_log_model_class': topic_models.TopicCommitLogEntryModel,
            'id_string_format': 'rights-%s-%s'
        },
        'CollectionRightsSnapshotMetadataModel': {
            'parent_model_class': collection_models.CollectionRightsModel,
            'commit_log_model_class': (
                collection_models.CollectionCommitLogEntryModel),
            'id_string_format': 'rights-%s-%s'
        },
        'ExplorationRightsSnapshotMetadataModel': {
            'parent_model_class': exp_models.ExplorationRightsModel,
            'commit_log_model_class': exp_models.ExplorationCommitLogEntryModel,
            'id_string_format': 'rights-%s-%s'
        },
    }
    # This list consists of the rights snapshot metadata models for which
    # the commit log model is not created when the commit cmd is "create"
    # or "delete".
    MODEL_NAMES_WITH_PARTIAL_COMMIT_LOGS = [
        'CollectionRightsSnapshotMetadataModel',
        'ExplorationRightsSnapshotMetadataModel'
    ]

    @classmethod
    def entity_classes_to_map_over(cls):
        """Return a list of SnapshotMetadata models that is associated
        with a CommitLogEntry model.
        """
        return ValidateSnapshotMetadataModelsJob.SNAPSHOT_METADATA_MODELS

    @staticmethod
    def map(snapshot_model):
        """Implements the map function for this job."""
        job_class = ValidateSnapshotMetadataModelsJob
        class_name = snapshot_model.__class__.__name__
        missing_commit_log_msg = (
            '%s - MISSING COMMIT LOGS' % job_class.FAILURE_PREFIX)
        found_commit_log_msg = 'FOUND COMMIT LOGS'

        # Note: The subtopic snapshot ID is in the format
        # '<topicId>-<subtopicNum>-<version>'.
        model_id, version = snapshot_model.id.rsplit('-', 1)
        model_properties = job_class.MODEL_NAMES_TO_PROPERTIES[class_name]
        commit_log_id = (
            model_properties['id_string_format'] % (model_id, version))
        parent_model_class = (
            model_properties['parent_model_class'].get_by_id(model_id))
        commit_log_model_class = (
            model_properties['commit_log_model_class'].get_by_id(
                commit_log_id))
        if class_name in job_class.MODEL_NAMES_WITH_PARTIAL_COMMIT_LOGS:
            if snapshot_model.commit_type in ['create', 'delete']:
                missing_commit_log_msg = (
                    'COMMIT LOGS SHOULD NOT EXIST AND DOES NOT EXIST')
                found_commit_log_msg = (
                    '%s - COMMIT LOGS SHOULD NOT EXIST BUT EXISTS' % (
                        job_class.FAILURE_PREFIX))

        message_prefix = (
            missing_commit_log_msg if commit_log_model_class is None
            else found_commit_log_msg)
        yield ('%s - %s' % (message_prefix, class_name), snapshot_model.id)

        if parent_model_class is None:
            yield (
                '%s - MISSING PARENT MODEL - %s' % (
                    job_class.FAILURE_PREFIX, class_name),
                snapshot_model.id)
        else:
            yield ('FOUND PARENT MODEL - %s' % class_name, 1)

    @staticmethod
    def reduce(key, values):
        """Implements the reduce function for this job."""
        if key.startswith(ValidateSnapshotMetadataModelsJob.FAILURE_PREFIX):
            yield (key, values)
        else:
            yield (key, len(values))
