CREATE TYPE "public"."measure_source" AS ENUM('user', 'ballotpedia');--> statement-breakpoint
CREATE TYPE "public"."measure_status" AS ENUM('draft', 'open', 'closed');--> statement-breakpoint
CREATE TABLE "ballot_measure" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"created_by" uuid NOT NULL,
	"source" "measure_source" DEFAULT 'user' NOT NULL,
	"external_id" text,
	"source_url" text,
	"source_data" jsonb,
	"title" text NOT NULL,
	"summary" text NOT NULL,
	"description" text,
	"ballot_type" "ballot_type" DEFAULT 'single_choice' NOT NULL,
	"status" "measure_status" DEFAULT 'draft' NOT NULL,
	"jurisdiction" text,
	"measure_date" date,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "ballot_measure_source_external_id_unique" UNIQUE("source","external_id")
);
--> statement-breakpoint
CREATE TABLE "electorate" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" text NOT NULL,
	"description" text,
	"generator" text NOT NULL,
	"generation_params" jsonb NOT NULL,
	"seed" bigint NOT NULL,
	"voter_count" integer NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "measure_option" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"measure_id" uuid NOT NULL,
	"ordinal" integer NOT NULL,
	"label" text NOT NULL,
	"description" text,
	CONSTRAINT "measure_option_measure_id_ordinal_unique" UNIQUE("measure_id","ordinal")
);
--> statement-breakpoint
CREATE TABLE "measure_topic" (
	"measure_id" uuid NOT NULL,
	"domain_id" uuid NOT NULL,
	"program_id" uuid,
	"is_primary" boolean DEFAULT true NOT NULL,
	CONSTRAINT "measure_topic_measure_id_domain_id_pk" PRIMARY KEY("measure_id","domain_id")
);
--> statement-breakpoint
CREATE TABLE "resolution_run" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"measure_id" uuid NOT NULL,
	"electorate_id" uuid NOT NULL,
	"method" text NOT NULL,
	"seed" bigint NOT NULL,
	"result" jsonb NOT NULL,
	"computed_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "resolution_run_cache_key_unique" UNIQUE("measure_id","electorate_id","method","seed")
);
--> statement-breakpoint
DROP TABLE "election_option" CASCADE;--> statement-breakpoint
DROP TABLE "election_topic" CASCADE;--> statement-breakpoint
DROP TABLE "election" CASCADE;--> statement-breakpoint
ALTER TABLE "ballot_measure" ADD CONSTRAINT "ballot_measure_created_by_app_user_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."app_user"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "measure_option" ADD CONSTRAINT "measure_option_measure_id_ballot_measure_id_fk" FOREIGN KEY ("measure_id") REFERENCES "public"."ballot_measure"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "measure_topic" ADD CONSTRAINT "measure_topic_measure_id_ballot_measure_id_fk" FOREIGN KEY ("measure_id") REFERENCES "public"."ballot_measure"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "measure_topic" ADD CONSTRAINT "measure_topic_domain_id_domain_id_fk" FOREIGN KEY ("domain_id") REFERENCES "public"."domain"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "measure_topic" ADD CONSTRAINT "measure_topic_program_id_program_id_fk" FOREIGN KEY ("program_id") REFERENCES "public"."program"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "resolution_run" ADD CONSTRAINT "resolution_run_measure_id_ballot_measure_id_fk" FOREIGN KEY ("measure_id") REFERENCES "public"."ballot_measure"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "resolution_run" ADD CONSTRAINT "resolution_run_electorate_id_electorate_id_fk" FOREIGN KEY ("electorate_id") REFERENCES "public"."electorate"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
DROP TYPE "public"."election_source";--> statement-breakpoint
DROP TYPE "public"."election_status";