CREATE TYPE "public"."proposal_status" AS ENUM('draft', 'active', 'passed', 'failed', 'archived');--> statement-breakpoint
CREATE TABLE "domain" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" text NOT NULL,
	"active" boolean DEFAULT true NOT NULL,
	CONSTRAINT "domain_name_unique" UNIQUE("name")
);
--> statement-breakpoint
CREATE TABLE "program" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"domain_id" uuid NOT NULL,
	"name" text NOT NULL,
	"active" boolean DEFAULT true NOT NULL
);
--> statement-breakpoint
CREATE TABLE "proposal_action" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"proposal_id" uuid NOT NULL,
	"ordinal" integer NOT NULL,
	"text" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "proposal_budget_item" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"proposal_id" uuid NOT NULL,
	"item_name" text NOT NULL,
	"one_time_usd" integer DEFAULT 0 NOT NULL,
	"annual_usd" integer DEFAULT 0 NOT NULL,
	"confidence" numeric(3, 2) DEFAULT '0.50' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "proposal_metric" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"proposal_id" uuid NOT NULL,
	"name" text NOT NULL,
	"unit" text NOT NULL,
	"baseline_val" numeric(12, 4) NOT NULL,
	"baseline_year" integer,
	"baseline_source" text,
	"target_val" numeric(12, 4) NOT NULL,
	"deadline" date NOT NULL
);
--> statement-breakpoint
CREATE TABLE "proposal_topic" (
	"proposal_id" uuid NOT NULL,
	"domain_id" uuid NOT NULL,
	"program_id" uuid,
	"is_primary" boolean DEFAULT true NOT NULL
);
--> statement-breakpoint
CREATE TABLE "proposal" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"author_id" uuid NOT NULL,
	"status" "proposal_status" DEFAULT 'draft' NOT NULL,
	"title" text NOT NULL,
	"summary" text NOT NULL,
	"problem_plain" text NOT NULL,
	"implementing_org" text,
	"scope_geojson" text,
	"population_estimate" integer,
	"population_source" text,
	"budget_one_time_usd" integer DEFAULT 0 NOT NULL,
	"budget_annual_usd" integer DEFAULT 0 NOT NULL,
	"funding_notes" text,
	"legal_citation" text,
	"needs_new_authority" boolean DEFAULT false NOT NULL,
	"equity_beneficiaries" text,
	"equity_cost_bearers" text,
	"safeguards_rollback_trigger" text,
	"safeguards_rollback_steps" text,
	"sunset_date" date,
	"privacy_notes" text,
	"retention_days" integer,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "program" ADD CONSTRAINT "program_domain_id_domain_id_fk" FOREIGN KEY ("domain_id") REFERENCES "public"."domain"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "proposal_action" ADD CONSTRAINT "proposal_action_proposal_id_proposal_id_fk" FOREIGN KEY ("proposal_id") REFERENCES "public"."proposal"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "proposal_budget_item" ADD CONSTRAINT "proposal_budget_item_proposal_id_proposal_id_fk" FOREIGN KEY ("proposal_id") REFERENCES "public"."proposal"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "proposal_metric" ADD CONSTRAINT "proposal_metric_proposal_id_proposal_id_fk" FOREIGN KEY ("proposal_id") REFERENCES "public"."proposal"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "proposal_topic" ADD CONSTRAINT "proposal_topic_proposal_id_proposal_id_fk" FOREIGN KEY ("proposal_id") REFERENCES "public"."proposal"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "proposal_topic" ADD CONSTRAINT "proposal_topic_domain_id_domain_id_fk" FOREIGN KEY ("domain_id") REFERENCES "public"."domain"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "proposal_topic" ADD CONSTRAINT "proposal_topic_program_id_program_id_fk" FOREIGN KEY ("program_id") REFERENCES "public"."program"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "proposal" ADD CONSTRAINT "proposal_author_id_app_user_id_fk" FOREIGN KEY ("author_id") REFERENCES "public"."app_user"("id") ON DELETE restrict ON UPDATE no action;