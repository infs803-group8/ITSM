-- ============================================================================
-- IT Service Desk - MySQL Final Schema v1.0
-- Target: MySQL 8.0 / 8.4 and Amazon RDS for MySQL 8.4
-- Unified database name for local development and AWS RDS: service_desk
-- Character set: utf8mb4; timestamps: UTC; storage engine: InnoDB
--
-- IMPORTANT
-- 1. Run this file against a new/empty MySQL instance or schema.
-- 2. This file intentionally does not DROP an existing database or table.
-- 3. It creates no demo account, real user, vendor, password, or AWS secret.
-- 4. Application passwords must be stored only as strong password hashes.
-- 5. Schema changes after freeze require a separately reviewed SQL patch.
-- ============================================================================

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
SET time_zone = '+00:00';
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

CREATE DATABASE IF NOT EXISTS `service_desk`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE `service_desk`;

-- --------------------------------------------------------------------------
-- 1. Schema identity and reference/configuration tables
-- --------------------------------------------------------------------------

CREATE TABLE `schema_metadata` (
  `schema_id` TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'Singleton row identifier',
  `schema_name` VARCHAR(100) NOT NULL COMMENT 'Logical schema name',
  `schema_version` VARCHAR(20) NOT NULL COMMENT 'Release schema version',
  `installed_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`schema_id`),
  CONSTRAINT `chk_schema_metadata_singleton` CHECK (`schema_id` = 1)
) ENGINE=InnoDB COMMENT='Installed database schema identity and version';

CREATE TABLE `roles` (
  `role_code` VARCHAR(32) NOT NULL COMMENT 'Stable API role code',
  `display_name` VARCHAR(100) NOT NULL,
  `description` VARCHAR(500) NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`role_code`),
  CONSTRAINT `chk_roles_is_active` CHECK (`is_active` IN (0, 1))
) ENGINE=InnoDB COMMENT='System roles used by authentication and authorisation';

CREATE TABLE `categories` (
  `category_code` VARCHAR(32) NOT NULL COMMENT 'Stable API category code',
  `display_name` VARCHAR(100) NOT NULL,
  `description` VARCHAR(500) NULL,
  `sort_order` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`category_code`),
  CONSTRAINT `chk_categories_is_active` CHECK (`is_active` IN (0, 1))
) ENGINE=InnoDB COMMENT='Ticket categories and engineer skill categories';

CREATE TABLE `priorities` (
  `priority_code` VARCHAR(16) NOT NULL COMMENT 'Stable API priority code',
  `display_name` VARCHAR(100) NOT NULL,
  `description` VARCHAR(500) NULL,
  `sort_order` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`priority_code`),
  CONSTRAINT `chk_priorities_is_active` CHECK (`is_active` IN (0, 1))
) ENGINE=InnoDB COMMENT='Ticket priorities';

CREATE TABLE `ticket_statuses` (
  `status_code` VARCHAR(32) NOT NULL COMMENT 'Stable internal ticket status code',
  `display_name` VARCHAR(100) NOT NULL,
  `description` VARCHAR(500) NULL,
  `sort_order` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `is_api_visible` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'NEW is internal only',
  PRIMARY KEY (`status_code`),
  CONSTRAINT `chk_ticket_statuses_visible` CHECK (`is_api_visible` IN (0, 1))
) ENGINE=InnoDB COMMENT='Ticket lifecycle statuses';

CREATE TABLE `sla_statuses` (
  `sla_status_code` VARCHAR(16) NOT NULL COMMENT 'Stable SLA state code',
  `display_name` VARCHAR(100) NOT NULL,
  `description` VARCHAR(500) NULL,
  `sort_order` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`sla_status_code`)
) ENGINE=InnoDB COMMENT='Current engineering SLA states';

CREATE TABLE `service_config` (
  `config_id` TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'Singleton row identifier',
  `engineering_sla_hours` SMALLINT UNSIGNED NOT NULL DEFAULT 48,
  `at_risk_percent` TINYINT UNSIGNED NOT NULL DEFAULT 80,
  `user_response_hours` SMALLINT UNSIGNED NOT NULL DEFAULT 120,
  `resolved_window_hours` SMALLINT UNSIGNED NOT NULL DEFAULT 168,
  `attachment_max_size_bytes` BIGINT UNSIGNED NOT NULL DEFAULT 10485760,
  `upload_url_ttl_seconds` INT UNSIGNED NOT NULL DEFAULT 900,
  `download_url_ttl_seconds` INT UNSIGNED NOT NULL DEFAULT 300,
  `sla_monitor_interval_minutes` SMALLINT UNSIGNED NOT NULL DEFAULT 5,
  `attachment_cleanup_interval_minutes` SMALLINT UNSIGNED NOT NULL DEFAULT 30,
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`config_id`),
  CONSTRAINT `chk_service_config_singleton` CHECK (`config_id` = 1),
  CONSTRAINT `chk_service_config_at_risk` CHECK (`at_risk_percent` BETWEEN 1 AND 100),
  CONSTRAINT `chk_service_config_positive` CHECK (
    `engineering_sla_hours` > 0
    AND `user_response_hours` > 0
    AND `resolved_window_hours` > 0
    AND `attachment_max_size_bytes` > 0
    AND `upload_url_ttl_seconds` > 0
    AND `download_url_ttl_seconds` > 0
    AND `sla_monitor_interval_minutes` > 0
    AND `attachment_cleanup_interval_minutes` > 0
  )
) ENGINE=InnoDB COMMENT='Single source of timer and attachment limits for API-12';

CREATE TABLE `allowed_attachment_types` (
  `extension` VARCHAR(16) NOT NULL COMMENT 'Lowercase extension without a dot',
  `content_type` VARCHAR(100) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `description` VARCHAR(200) NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`extension`),
  KEY `idx_allowed_attachment_types_mime` (`content_type`, `is_active`),
  CONSTRAINT `chk_allowed_attachment_types_active` CHECK (`is_active` IN (0, 1)),
  CONSTRAINT `chk_allowed_attachment_types_lower` CHECK (`extension` = LOWER(`extension`))
) ENGINE=InnoDB COMMENT='Allowed extension and MIME pairs returned by API-12';

-- --------------------------------------------------------------------------
-- 2. Identity, vendor organisation, engineer skills and assignment lock
-- --------------------------------------------------------------------------

CREATE TABLE `vendor_organisations` (
  `vendor_org_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(200) NOT NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`vendor_org_id`),
  UNIQUE KEY `uq_vendor_organisations_name` (`name`),
  KEY `idx_vendor_organisations_active_name` (`is_active`, `name`),
  CONSTRAINT `chk_vendor_organisations_active` CHECK (`is_active` IN (0, 1))
) ENGINE=InnoDB COMMENT='External vendor organisations available for vendor requests';

CREATE TABLE `users` (
  `user_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `email` VARCHAR(254) NOT NULL COMMENT 'Normalised lowercase login email',
  `password_hash` VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `display_name` VARCHAR(100) NOT NULL,
  `role_code` VARCHAR(32) NOT NULL,
  `is_available` TINYINT(1) NULL COMMENT 'Required only for Tier 1/Tier 2 engineers',
  `vendor_org_id` BIGINT UNSIGNED NULL COMMENT 'Required only for EXTERNAL_VENDOR',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Disable account instead of deleting it',
  `last_assigned_at` DATETIME(6) NULL COMMENT 'Auto-assignment stable ordering',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `uq_users_email` (`email`),
  KEY `idx_users_engineer_candidates`
    (`role_code`, `is_active`, `is_available`, `last_assigned_at`, `user_id`),
  KEY `idx_users_vendor_scope` (`vendor_org_id`, `is_active`, `user_id`),
  CONSTRAINT `fk_users_role`
    FOREIGN KEY (`role_code`) REFERENCES `roles` (`role_code`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_users_vendor_org`
    FOREIGN KEY (`vendor_org_id`) REFERENCES `vendor_organisations` (`vendor_org_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `chk_users_email_normalised` CHECK (`email` = LOWER(TRIM(`email`))),
  CONSTRAINT `chk_users_display_name` CHECK (CHAR_LENGTH(TRIM(`display_name`)) BETWEEN 1 AND 100),
  CONSTRAINT `chk_users_flags` CHECK (
    `is_active` IN (0, 1) AND (`is_available` IS NULL OR `is_available` IN (0, 1))
  ),
  CONSTRAINT `chk_users_engineer_availability` CHECK (
    (`role_code` IN ('ENGINEER_TIER1', 'ENGINEER_TIER2') AND `is_available` IS NOT NULL)
    OR
    (`role_code` NOT IN ('ENGINEER_TIER1', 'ENGINEER_TIER2') AND `is_available` IS NULL)
  ),
  CONSTRAINT `chk_users_vendor_binding` CHECK (
    (`role_code` = 'EXTERNAL_VENDOR' AND `vendor_org_id` IS NOT NULL)
    OR
    (`role_code` <> 'EXTERNAL_VENDOR' AND `vendor_org_id` IS NULL)
  )
) ENGINE=InnoDB COMMENT='All requester, engineer, manager and vendor login accounts';

CREATE TABLE `user_skills` (
  `user_id` BIGINT UNSIGNED NOT NULL,
  `category_code` VARCHAR(32) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`user_id`, `category_code`),
  KEY `idx_user_skills_category_user` (`category_code`, `user_id`),
  CONSTRAINT `fk_user_skills_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_user_skills_category`
    FOREIGN KEY (`category_code`) REFERENCES `categories` (`category_code`)
    ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB COMMENT='Many-to-many mapping between engineers and ticket categories';

CREATE TABLE `assignment_control` (
  `control_id` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  `control_name` VARCHAR(50) NOT NULL DEFAULT 'INITIAL_ASSIGNMENT',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`control_id`),
  UNIQUE KEY `uq_assignment_control_name` (`control_name`),
  CONSTRAINT `chk_assignment_control_singleton` CHECK (`control_id` = 1)
) ENGINE=InnoDB COMMENT='Singleton row locked to serialise initial auto-assignment';

-- --------------------------------------------------------------------------
-- 3. Ticket core and comments
-- --------------------------------------------------------------------------

CREATE TABLE `tickets` (
  `ticket_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `requester_id` BIGINT UNSIGNED NOT NULL,
  `title` VARCHAR(200) NOT NULL,
  `description` TEXT NOT NULL,
  `category_code` VARCHAR(32) NOT NULL,
  `priority_code` VARCHAR(16) NOT NULL,
  `status_code` VARCHAR(32) NOT NULL DEFAULT 'NEW',
  `assignee_id` BIGINT UNSIGNED NULL,
  `last_resolved_assignee_id` BIGINT UNSIGNED NULL
    COMMENT 'Assignee saved at resolution for reopen preference',
  `sla_cycle_no` INT UNSIGNED NOT NULL DEFAULT 1,
  `sla_status_code` VARCHAR(16) NOT NULL DEFAULT 'ON_TRACK',
  `sla_started_at` DATETIME(6) NULL,
  `sla_deadline` DATETIME(6) NULL,
  `pending_user_reason` VARCHAR(32) NULL,
  `pending_user_deadline` DATETIME(6) NULL,
  `resolution_summary` TEXT NULL,
  `resolution_type` VARCHAR(64) NULL,
  `resolved_at` DATETIME(6) NULL,
  `auto_close_at` DATETIME(6) NULL,
  `closure_type` VARCHAR(32) NULL,
  `closed_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`ticket_id`),
  KEY `idx_tickets_requester_list` (`requester_id`, `created_at`, `ticket_id`),
  KEY `idx_tickets_assignee_queue`
    (`assignee_id`, `status_code`, `sla_status_code`, `sla_deadline`, `ticket_id`),
  KEY `idx_tickets_manager_filters`
    (`status_code`, `category_code`, `priority_code`, `created_at`, `ticket_id`),
  KEY `idx_tickets_sla_monitor`
    (`sla_status_code`, `sla_deadline`, `status_code`, `ticket_id`),
  KEY `idx_tickets_pending_user_job`
    (`status_code`, `pending_user_deadline`, `ticket_id`),
  KEY `idx_tickets_auto_close_job`
    (`status_code`, `auto_close_at`, `ticket_id`),
  CONSTRAINT `fk_tickets_requester`
    FOREIGN KEY (`requester_id`) REFERENCES `users` (`user_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_tickets_assignee`
    FOREIGN KEY (`assignee_id`) REFERENCES `users` (`user_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_tickets_last_resolved_assignee`
    FOREIGN KEY (`last_resolved_assignee_id`) REFERENCES `users` (`user_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_tickets_category`
    FOREIGN KEY (`category_code`) REFERENCES `categories` (`category_code`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_tickets_priority`
    FOREIGN KEY (`priority_code`) REFERENCES `priorities` (`priority_code`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_tickets_status`
    FOREIGN KEY (`status_code`) REFERENCES `ticket_statuses` (`status_code`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_tickets_sla_status`
    FOREIGN KEY (`sla_status_code`) REFERENCES `sla_statuses` (`sla_status_code`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `chk_tickets_title` CHECK (CHAR_LENGTH(TRIM(`title`)) BETWEEN 1 AND 200),
  CONSTRAINT `chk_tickets_description` CHECK (CHAR_LENGTH(TRIM(`description`)) BETWEEN 1 AND 5000),
  CONSTRAINT `chk_tickets_cycle` CHECK (`sla_cycle_no` >= 1),
  CONSTRAINT `chk_tickets_sla_times` CHECK (
    (`sla_started_at` IS NULL AND `sla_deadline` IS NULL)
    OR (`sla_started_at` IS NOT NULL AND `sla_deadline` IS NOT NULL
        AND `sla_deadline` > `sla_started_at`)
  ),
  CONSTRAINT `chk_tickets_assignee_by_status` CHECK (
    (`status_code` = 'UNASSIGNED' AND `assignee_id` IS NULL)
    OR (`status_code` IN ('ASSIGNED', 'IN_PROGRESS', 'PENDING_USER', 'PENDING_VENDOR')
        AND `assignee_id` IS NOT NULL)
    OR (`status_code` IN ('NEW', 'REOPENED', 'RESOLVED', 'CLOSED'))
  ),
  CONSTRAINT `chk_tickets_pending_user` CHECK (
    (`status_code` = 'PENDING_USER'
      AND `pending_user_reason` IN ('INFORMATION_REQUIRED', 'RESOLUTION_CONFIRMATION')
      AND `pending_user_deadline` IS NOT NULL)
    OR
    (`status_code` <> 'PENDING_USER'
      AND `pending_user_reason` IS NULL
      AND `pending_user_deadline` IS NULL)
  ),
  CONSTRAINT `chk_tickets_resolution` CHECK (
    (`status_code` IN ('RESOLVED', 'CLOSED')
      AND `resolution_summary` IS NOT NULL
      AND `resolution_type` IN
        ('USER_CONFIRMED', 'AUTO_NO_USER_RESPONSE', 'AUTO_CONFIRMATION_TIMEOUT')
      AND `resolved_at` IS NOT NULL
      AND `auto_close_at` IS NOT NULL
      AND `auto_close_at` > `resolved_at`)
    OR
    (`status_code` = 'PENDING_USER'
      AND `pending_user_reason` = 'RESOLUTION_CONFIRMATION'
      AND `resolution_summary` IS NOT NULL
      AND `resolution_type` IS NULL
      AND `resolved_at` IS NULL
      AND `auto_close_at` IS NULL)
    OR
    (`status_code` NOT IN ('RESOLVED', 'CLOSED')
      AND NOT (`status_code` = 'PENDING_USER'
               AND `pending_user_reason` = 'RESOLUTION_CONFIRMATION')
      AND `resolution_summary` IS NULL
      AND `resolution_type` IS NULL
      AND `resolved_at` IS NULL
      AND `auto_close_at` IS NULL)
  ),
  CONSTRAINT `chk_tickets_closure` CHECK (
    (`status_code` = 'CLOSED'
      AND `closure_type` IN ('MANUAL_USER', 'AUTO_AFTER_7_DAYS')
      AND `closed_at` IS NOT NULL)
    OR
    (`status_code` <> 'CLOSED'
      AND `closure_type` IS NULL
      AND `closed_at` IS NULL)
  )
) ENGINE=InnoDB COMMENT='Ticket core plus current workflow, SLA, resolution and closure snapshot';

CREATE TABLE `comments` (
  `comment_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `ticket_id` BIGINT UNSIGNED NOT NULL,
  `author_id` BIGINT UNSIGNED NOT NULL,
  `message` TEXT NOT NULL,
  `visibility` VARCHAR(32) NOT NULL,
  `comment_type` VARCHAR(16) NOT NULL DEFAULT 'ORDINARY',
  `workflow_action` VARCHAR(64) NULL
    COMMENT 'Internal action name when comment_type is WORKFLOW',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`comment_id`),
  KEY `idx_comments_ticket_time` (`ticket_id`, `created_at`, `comment_id`),
  KEY `idx_comments_author_time` (`author_id`, `created_at`, `comment_id`),
  CONSTRAINT `fk_comments_ticket`
    FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`ticket_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_comments_author`
    FOREIGN KEY (`author_id`) REFERENCES `users` (`user_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `chk_comments_message` CHECK (CHAR_LENGTH(TRIM(`message`)) BETWEEN 1 AND 4000),
  CONSTRAINT `chk_comments_visibility` CHECK (`visibility` IN ('USER_VISIBLE', 'INTERNAL_ONLY')),
  CONSTRAINT `chk_comments_type` CHECK (
    (`comment_type` = 'ORDINARY' AND `workflow_action` IS NULL)
    OR (`comment_type` = 'WORKFLOW' AND `workflow_action` IS NOT NULL)
  )
) ENGINE=InnoDB COMMENT='Ordinary and workflow comments; workflow state is changed by service code';

-- --------------------------------------------------------------------------
-- 4. Vendor collaboration
-- --------------------------------------------------------------------------

CREATE TABLE `vendor_requests` (
  `vendor_request_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `ticket_id` BIGINT UNSIGNED NOT NULL,
  `vendor_org_id` BIGINT UNSIGNED NOT NULL,
  `requested_by_id` BIGINT UNSIGNED NOT NULL COMMENT 'Tier 2 engineer who created the request',
  `vendor_message` TEXT NOT NULL COMMENT 'Vendor-safe, explicitly de-identified message',
  `status` VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  `responded_at` DATETIME(6) NULL,
  `cancelled_at` DATETIME(6) NULL,
  `cancelled_by_id` BIGINT UNSIGNED NULL,
  `cancellation_reason` VARCHAR(1000) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  `active_ticket_guard` BIGINT UNSIGNED GENERATED ALWAYS AS (
    CASE WHEN `status` = 'ACTIVE' THEN `ticket_id` ELSE NULL END
  ) STORED,
  PRIMARY KEY (`vendor_request_id`),
  UNIQUE KEY `uq_vendor_requests_one_active_per_ticket` (`active_ticket_guard`),
  KEY `idx_vendor_requests_ticket_history`
    (`ticket_id`, `created_at`, `vendor_request_id`),
  KEY `idx_vendor_requests_vendor_scope`
    (`vendor_org_id`, `status`, `created_at`, `vendor_request_id`),
  CONSTRAINT `fk_vendor_requests_ticket`
    FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`ticket_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_vendor_requests_vendor_org`
    FOREIGN KEY (`vendor_org_id`) REFERENCES `vendor_organisations` (`vendor_org_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_vendor_requests_requested_by`
    FOREIGN KEY (`requested_by_id`) REFERENCES `users` (`user_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_vendor_requests_cancelled_by`
    FOREIGN KEY (`cancelled_by_id`) REFERENCES `users` (`user_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `chk_vendor_requests_message`
    CHECK (CHAR_LENGTH(TRIM(`vendor_message`)) BETWEEN 1 AND 4000),
  CONSTRAINT `chk_vendor_requests_status`
    CHECK (`status` IN ('ACTIVE', 'RESPONDED', 'CANCELLED')),
  CONSTRAINT `chk_vendor_requests_status_times` CHECK (
    (`status` = 'ACTIVE'
      AND `responded_at` IS NULL
      AND `cancelled_at` IS NULL
      AND `cancelled_by_id` IS NULL
      AND `cancellation_reason` IS NULL)
    OR
    (`status` = 'RESPONDED'
      AND `responded_at` IS NOT NULL
      AND `cancelled_at` IS NULL
      AND `cancelled_by_id` IS NULL
      AND `cancellation_reason` IS NULL)
    OR
    (`status` = 'CANCELLED'
      AND `responded_at` IS NULL
      AND `cancelled_at` IS NOT NULL)
  )
) ENGINE=InnoDB COMMENT='Vendor-safe collaboration request; one ACTIVE request per ticket';

CREATE TABLE `vendor_responses` (
  `vendor_response_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `vendor_request_id` BIGINT UNSIGNED NOT NULL,
  `responder_id` BIGINT UNSIGNED NOT NULL COMMENT 'Vendor user who submitted the response',
  `message` TEXT NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`vendor_response_id`),
  UNIQUE KEY `uq_vendor_responses_request` (`vendor_request_id`),
  KEY `idx_vendor_responses_responder_time` (`responder_id`, `created_at`),
  CONSTRAINT `fk_vendor_responses_request`
    FOREIGN KEY (`vendor_request_id`) REFERENCES `vendor_requests` (`vendor_request_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_vendor_responses_responder`
    FOREIGN KEY (`responder_id`) REFERENCES `users` (`user_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `chk_vendor_responses_message`
    CHECK (CHAR_LENGTH(TRIM(`message`)) BETWEEN 1 AND 4000)
) ENGINE=InnoDB COMMENT='One formal response for each responded vendor request';

-- --------------------------------------------------------------------------
-- 5. S3 attachment upload session and verified attachment metadata
-- --------------------------------------------------------------------------

CREATE TABLE `attachment_uploads` (
  `upload_id` CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `ticket_id` BIGINT UNSIGNED NOT NULL,
  `creator_id` BIGINT UNSIGNED NOT NULL,
  `object_key` VARCHAR(1024) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `file_name` VARCHAR(255) NOT NULL,
  `expected_content_type` VARCHAR(100) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `expected_size` BIGINT UNSIGNED NOT NULL,
  `visibility` VARCHAR(32) NOT NULL,
  `vendor_request_id` BIGINT UNSIGNED NULL,
  `vendor_org_id` BIGINT UNSIGNED NULL,
  `status` VARCHAR(16) NOT NULL DEFAULT 'PENDING',
  `expires_at` DATETIME(6) NOT NULL,
  `completed_at` DATETIME(6) NULL,
  `expired_at` DATETIME(6) NULL,
  `aborted_at` DATETIME(6) NULL,
  `attachment_id` CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`upload_id`),
  UNIQUE KEY `uq_attachment_uploads_object_key` (`object_key`),
  UNIQUE KEY `uq_attachment_uploads_attachment` (`attachment_id`),
  KEY `idx_attachment_uploads_ticket_creator`
    (`ticket_id`, `creator_id`, `created_at`),
  KEY `idx_attachment_uploads_cleanup`
    (`status`, `expires_at`, `upload_id`),
  KEY `idx_attachment_uploads_vendor_scope`
    (`vendor_org_id`, `vendor_request_id`, `status`),
  CONSTRAINT `fk_attachment_uploads_ticket`
    FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`ticket_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_attachment_uploads_creator`
    FOREIGN KEY (`creator_id`) REFERENCES `users` (`user_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_attachment_uploads_vendor_request`
    FOREIGN KEY (`vendor_request_id`) REFERENCES `vendor_requests` (`vendor_request_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_attachment_uploads_vendor_org`
    FOREIGN KEY (`vendor_org_id`) REFERENCES `vendor_organisations` (`vendor_org_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `chk_attachment_uploads_file_name`
    CHECK (CHAR_LENGTH(TRIM(`file_name`)) BETWEEN 1 AND 255),
  CONSTRAINT `chk_attachment_uploads_size`
    CHECK (`expected_size` BETWEEN 1 AND 10485760),
  CONSTRAINT `chk_attachment_uploads_content_type`
    CHECK (`expected_content_type` IN
      ('image/png', 'image/jpeg', 'application/pdf', 'text/plain')),
  CONSTRAINT `chk_attachment_uploads_visibility`
    CHECK (`visibility` IN ('USER_VISIBLE', 'INTERNAL_ONLY', 'VENDOR_SHARED')),
  CONSTRAINT `chk_attachment_uploads_vendor_binding` CHECK (
    (`visibility` = 'VENDOR_SHARED'
      AND `vendor_request_id` IS NOT NULL
      AND `vendor_org_id` IS NOT NULL)
    OR
    (`visibility` <> 'VENDOR_SHARED'
      AND `vendor_request_id` IS NULL
      AND `vendor_org_id` IS NULL)
  ),
  CONSTRAINT `chk_attachment_uploads_status`
    CHECK (`status` IN ('PENDING', 'COMPLETED', 'EXPIRED', 'ABORTED')),
  CONSTRAINT `chk_attachment_uploads_state_fields` CHECK (
    (`status` = 'PENDING'
      AND `completed_at` IS NULL AND `expired_at` IS NULL AND `aborted_at` IS NULL
      AND `attachment_id` IS NULL)
    OR
    (`status` = 'COMPLETED'
      AND `completed_at` IS NOT NULL AND `expired_at` IS NULL AND `aborted_at` IS NULL
      AND `attachment_id` IS NOT NULL)
    OR
    (`status` = 'EXPIRED'
      AND `completed_at` IS NULL AND `expired_at` IS NOT NULL AND `aborted_at` IS NULL
      AND `attachment_id` IS NULL)
    OR
    (`status` = 'ABORTED'
      AND `completed_at` IS NULL AND `expired_at` IS NULL AND `aborted_at` IS NOT NULL
      AND `attachment_id` IS NULL)
  )
) ENGINE=InnoDB COMMENT='Persistent presigned-upload session used by API-02 and API-03';

CREATE TABLE `attachments` (
  `attachment_id` CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `upload_id` CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `ticket_id` BIGINT UNSIGNED NOT NULL,
  `creator_id` BIGINT UNSIGNED NOT NULL,
  `object_key` VARCHAR(1024) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `file_name` VARCHAR(255) NOT NULL,
  `verified_content_type` VARCHAR(100) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `verified_size` BIGINT UNSIGNED NOT NULL,
  `visibility` VARCHAR(32) NOT NULL,
  `vendor_request_id` BIGINT UNSIGNED NULL,
  `vendor_org_id` BIGINT UNSIGNED NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`attachment_id`),
  UNIQUE KEY `uq_attachments_upload` (`upload_id`),
  UNIQUE KEY `uq_attachments_object_key` (`object_key`),
  KEY `idx_attachments_ticket_visibility_time`
    (`ticket_id`, `visibility`, `created_at`, `attachment_id`),
  KEY `idx_attachments_vendor_scope`
    (`vendor_org_id`, `vendor_request_id`, `ticket_id`, `created_at`),
  CONSTRAINT `fk_attachments_upload`
    FOREIGN KEY (`upload_id`) REFERENCES `attachment_uploads` (`upload_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_attachments_ticket`
    FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`ticket_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_attachments_creator`
    FOREIGN KEY (`creator_id`) REFERENCES `users` (`user_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_attachments_vendor_request`
    FOREIGN KEY (`vendor_request_id`) REFERENCES `vendor_requests` (`vendor_request_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_attachments_vendor_org`
    FOREIGN KEY (`vendor_org_id`) REFERENCES `vendor_organisations` (`vendor_org_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `chk_attachments_file_name`
    CHECK (CHAR_LENGTH(TRIM(`file_name`)) BETWEEN 1 AND 255),
  CONSTRAINT `chk_attachments_size`
    CHECK (`verified_size` BETWEEN 1 AND 10485760),
  CONSTRAINT `chk_attachments_content_type`
    CHECK (`verified_content_type` IN
      ('image/png', 'image/jpeg', 'application/pdf', 'text/plain')),
  CONSTRAINT `chk_attachments_visibility`
    CHECK (`visibility` IN ('USER_VISIBLE', 'INTERNAL_ONLY', 'VENDOR_SHARED')),
  CONSTRAINT `chk_attachments_vendor_binding` CHECK (
    (`visibility` = 'VENDOR_SHARED'
      AND `vendor_request_id` IS NOT NULL
      AND `vendor_org_id` IS NOT NULL)
    OR
    (`visibility` <> 'VENDOR_SHARED'
      AND `vendor_request_id` IS NULL
      AND `vendor_org_id` IS NULL)
  )
) ENGINE=InnoDB COMMENT='Verified attachment metadata; file bytes remain in private S3';

ALTER TABLE `attachment_uploads`
  ADD CONSTRAINT `fk_attachment_uploads_attachment`
  FOREIGN KEY (`attachment_id`) REFERENCES `attachments` (`attachment_id`)
  ON UPDATE RESTRICT ON DELETE RESTRICT;

-- --------------------------------------------------------------------------
-- 6. Append-only audit timeline
-- --------------------------------------------------------------------------

CREATE TABLE `ticket_events` (
  `event_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `ticket_id` BIGINT UNSIGNED NOT NULL,
  `event_type` VARCHAR(64) NOT NULL,
  `scope` VARCHAR(32) NOT NULL,
  `actor_id` BIGINT UNSIGNED NULL COMMENT 'NULL means a system-generated event',
  `vendor_org_id` BIGINT UNSIGNED NULL COMMENT 'Required only for VENDOR_SCOPE',
  `cycle_no` INT UNSIGNED NULL,
  `comment_id` BIGINT UNSIGNED NULL,
  `attachment_id` CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `vendor_request_id` BIGINT UNSIGNED NULL,
  `metadata` JSON NOT NULL DEFAULT (JSON_OBJECT())
    COMMENT 'Minimal non-secret event metadata; never duplicate complete payloads',
  `occurred_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `cycle_guard_ticket_id` BIGINT UNSIGNED GENERATED ALWAYS AS (
    CASE
      WHEN `event_type` IN
        ('SLA_CYCLE_STARTED', 'SLA_PAUSED', 'SLA_AT_RISK', 'SLA_OVERDUE', 'SLA_MET')
        AND `cycle_no` IS NOT NULL
      THEN `ticket_id` ELSE NULL
    END
  ) STORED,
  `cycle_guard_cycle_no` INT UNSIGNED GENERATED ALWAYS AS (
    CASE
      WHEN `event_type` IN
        ('SLA_CYCLE_STARTED', 'SLA_PAUSED', 'SLA_AT_RISK', 'SLA_OVERDUE', 'SLA_MET')
        AND `cycle_no` IS NOT NULL
      THEN `cycle_no` ELSE NULL
    END
  ) STORED,
  `cycle_guard_event_type` VARCHAR(64) GENERATED ALWAYS AS (
    CASE
      WHEN `event_type` IN
        ('SLA_CYCLE_STARTED', 'SLA_PAUSED', 'SLA_AT_RISK', 'SLA_OVERDUE', 'SLA_MET')
        AND `cycle_no` IS NOT NULL
      THEN `event_type` ELSE NULL
    END
  ) STORED,
  PRIMARY KEY (`event_id`),
  UNIQUE KEY `uq_ticket_events_cycle_guard`
    (`cycle_guard_ticket_id`, `cycle_guard_cycle_no`, `cycle_guard_event_type`),
  UNIQUE KEY `uq_ticket_events_comment` (`comment_id`),
  UNIQUE KEY `uq_ticket_events_attachment` (`attachment_id`),
  KEY `idx_ticket_events_ticket_scope_time`
    (`ticket_id`, `scope`, `occurred_at`, `event_id`),
  KEY `idx_ticket_events_type_time`
    (`event_type`, `occurred_at`, `event_id`),
  KEY `idx_ticket_events_vendor_scope`
    (`vendor_org_id`, `ticket_id`, `occurred_at`, `event_id`),
  KEY `idx_ticket_events_vendor_request` (`vendor_request_id`, `occurred_at`),
  CONSTRAINT `fk_ticket_events_ticket`
    FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`ticket_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_ticket_events_actor`
    FOREIGN KEY (`actor_id`) REFERENCES `users` (`user_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_ticket_events_vendor_org`
    FOREIGN KEY (`vendor_org_id`) REFERENCES `vendor_organisations` (`vendor_org_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_ticket_events_comment`
    FOREIGN KEY (`comment_id`) REFERENCES `comments` (`comment_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_ticket_events_attachment`
    FOREIGN KEY (`attachment_id`) REFERENCES `attachments` (`attachment_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `fk_ticket_events_vendor_request`
    FOREIGN KEY (`vendor_request_id`) REFERENCES `vendor_requests` (`vendor_request_id`)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT `chk_ticket_events_type` CHECK (`event_type` IN (
    'TICKET_CREATED', 'AUTO_ASSIGNED', 'ASSIGNED', 'REASSIGNED',
    'HANDLING_STARTED', 'COMMENT_ADDED', 'SLA_CYCLE_STARTED', 'SLA_PAUSED',
    'SLA_AT_RISK', 'SLA_OVERDUE', 'SLA_MET', 'USER_INFO_REQUESTED',
    'USER_RESUMED', 'VENDOR_REQUESTED', 'VENDOR_RESPONDED', 'VENDOR_CANCELLED',
    'RESOLUTION_SUBMITTED', 'RESOLUTION_CONFIRMED',
    'AUTO_RESOLVED_NO_USER_RESPONSE', 'RESOLUTION_CONFIRMATION_TIMEOUT',
    'TICKET_REOPENED', 'TICKET_CLOSED_MANUAL', 'TICKET_CLOSED_AUTO',
    'ATTACHMENT_ADDED'
  )),
  CONSTRAINT `chk_ticket_events_scope`
    CHECK (`scope` IN ('USER_VISIBLE', 'INTERNAL_ONLY', 'VENDOR_SCOPE')),
  CONSTRAINT `chk_ticket_events_vendor_scope` CHECK (
    (`scope` = 'VENDOR_SCOPE' AND `vendor_org_id` IS NOT NULL)
    OR (`scope` <> 'VENDOR_SCOPE' AND `vendor_org_id` IS NULL)
  ),
  CONSTRAINT `chk_ticket_events_cycle` CHECK (`cycle_no` IS NULL OR `cycle_no` >= 1),
  CONSTRAINT `chk_ticket_events_comment_type` CHECK (
    (`event_type` = 'COMMENT_ADDED' AND `comment_id` IS NOT NULL)
    OR (`event_type` <> 'COMMENT_ADDED' AND `comment_id` IS NULL)
  ),
  CONSTRAINT `chk_ticket_events_attachment_type` CHECK (
    (`event_type` = 'ATTACHMENT_ADDED' AND `attachment_id` IS NOT NULL)
    OR (`event_type` <> 'ATTACHMENT_ADDED' AND `attachment_id` IS NULL)
  )
) ENGINE=InnoDB COMMENT='Append-only, role-scoped ticket audit timeline';

DELIMITER $$

CREATE TRIGGER `trg_ticket_events_no_update`
BEFORE UPDATE ON `ticket_events`
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'ticket_events is append-only; UPDATE is not allowed';
END$$

CREATE TRIGGER `trg_ticket_events_no_delete`
BEFORE DELETE ON `ticket_events`
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'ticket_events is append-only; DELETE is not allowed';
END$$

DELIMITER ;

-- --------------------------------------------------------------------------
-- 7. Non-secret reference/configuration seed data
-- --------------------------------------------------------------------------

INSERT INTO `schema_metadata`
  (`schema_id`, `schema_name`, `schema_version`)
VALUES
  (1, 'IT Service Desk', '1.0');

INSERT INTO `roles`
  (`role_code`, `display_name`, `description`, `is_active`)
VALUES
  ('USER', 'Requester', 'Creates and follows own tickets', 1),
  ('ENGINEER_TIER1', 'Tier 1 Engineer', 'First-line service desk engineer', 1),
  ('ENGINEER_TIER2', 'Tier 2 Engineer', 'Advanced engineer and vendor coordinator', 1),
  ('EXTERNAL_VENDOR', 'External Vendor', 'Responds only to requests for own organisation', 1),
  ('SERVICE_DESK_MANAGER', 'Service Desk Manager', 'Global service desk management scope', 1);

INSERT INTO `categories`
  (`category_code`, `display_name`, `description`, `sort_order`, `is_active`)
VALUES
  ('NETWORK', 'Network', 'Connectivity, routing, switching and network access', 10, 1),
  ('HARDWARE', 'Hardware', 'Physical device and peripheral issues', 20, 1),
  ('SOFTWARE', 'Software', 'Application installation and software issues', 30, 1),
  ('ACCOUNT', 'Account', 'Identity, password and access issues', 40, 1),
  ('OTHER', 'Other', 'Requests not covered by another category', 50, 1);

INSERT INTO `priorities`
  (`priority_code`, `display_name`, `description`, `sort_order`, `is_active`)
VALUES
  ('LOW', 'Low', 'Low business impact', 10, 1),
  ('MEDIUM', 'Medium', 'Normal business impact', 20, 1),
  ('HIGH', 'High', 'Significant business impact', 30, 1),
  ('URGENT', 'Urgent', 'Critical business impact', 40, 1);

INSERT INTO `ticket_statuses`
  (`status_code`, `display_name`, `description`, `sort_order`, `is_api_visible`)
VALUES
  ('NEW', 'New', 'Internal transient creation status', 0, 0),
  ('UNASSIGNED', 'Unassigned', 'No eligible assignee', 10, 1),
  ('ASSIGNED', 'Assigned', 'Assigned but not started', 20, 1),
  ('IN_PROGRESS', 'In Progress', 'Engineer is working', 30, 1),
  ('PENDING_USER', 'Pending User', 'Waiting for requester action', 40, 1),
  ('PENDING_VENDOR', 'Pending Vendor', 'Internal wait for vendor response', 50, 1),
  ('RESOLVED', 'Resolved', 'Resolved and inside reopen window', 60, 1),
  ('REOPENED', 'Reopened', 'Requester reopened the issue', 70, 1),
  ('CLOSED', 'Closed', 'Read-only terminal status', 80, 1);

INSERT INTO `sla_statuses`
  (`sla_status_code`, `display_name`, `description`, `sort_order`)
VALUES
  ('ON_TRACK', 'On Track', 'Before the at-risk threshold', 10),
  ('AT_RISK', 'At Risk', 'At or beyond 80 percent of the cycle', 20),
  ('OVERDUE', 'Overdue', 'Past the engineering SLA deadline', 30),
  ('PAUSED', 'Paused', 'Cycle paused while waiting for user information', 40),
  ('MET', 'Met', 'Cycle completed before its deadline', 50);

INSERT INTO `service_config`
  (`config_id`, `engineering_sla_hours`, `at_risk_percent`,
   `user_response_hours`, `resolved_window_hours`,
   `attachment_max_size_bytes`, `upload_url_ttl_seconds`,
   `download_url_ttl_seconds`, `sla_monitor_interval_minutes`,
   `attachment_cleanup_interval_minutes`)
VALUES
  (1, 48, 80, 120, 168, 10485760, 900, 300, 5, 30);

INSERT INTO `allowed_attachment_types`
  (`extension`, `content_type`, `description`, `is_active`)
VALUES
  ('png', 'image/png', 'PNG image', 1),
  ('jpg', 'image/jpeg', 'JPEG image', 1),
  ('jpeg', 'image/jpeg', 'JPEG image', 1),
  ('pdf', 'application/pdf', 'PDF document', 1),
  ('txt', 'text/plain', 'Plain text file', 1),
  ('log', 'text/plain', 'Log text file', 1);

INSERT INTO `assignment_control`
  (`control_id`, `control_name`)
VALUES
  (1, 'INITIAL_ASSIGNMENT');

-- --------------------------------------------------------------------------
-- 8. Optional post-install verification queries (read-only)
-- --------------------------------------------------------------------------

SELECT `schema_name`, `schema_version`, `installed_at`
FROM `schema_metadata`
WHERE `schema_id` = 1;

SELECT COUNT(*) AS `application_table_count`
FROM `information_schema`.`tables`
WHERE `table_schema` = 'service_desk'
  AND `table_type` = 'BASE TABLE';

SELECT `table_name`, `engine`, `table_collation`
FROM `information_schema`.`tables`
WHERE `table_schema` = 'service_desk'
ORDER BY `table_name`;

-- Expected result: 19 BASE TABLES, all using InnoDB and utf8mb4 collation.
