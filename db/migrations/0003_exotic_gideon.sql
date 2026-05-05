CREATE TYPE "public"."ballot_type" AS ENUM('single_choice', 'approval', 'ranked_choice', 'score', 'quadratic');--> statement-breakpoint
CREATE TYPE "public"."election_source" AS ENUM('user', 'ballotpedia');--> statement-breakpoint
CREATE TYPE "public"."election_status" AS ENUM('draft', 'open', 'closed');--> statement-breakpoint
CREATE TABLE "election_option" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"election_id" uuid NOT NULL,
	"ordinal" integer NOT NULL,
	"label" text NOT NULL,
	"description" text,
	CONSTRAINT "election_option_election_id_ordinal_unique" UNIQUE("election_id","ordinal")
);
--> statement-breakpoint
CREATE TABLE "election_topic" (
	"election_id" uuid NOT NULL,
	"domain_id" uuid NOT NULL,
	"program_id" uuid,
	"is_primary" boolean DEFAULT true NOT NULL,
	CONSTRAINT "election_topic_election_id_domain_id_pk" PRIMARY KEY("election_id","domain_id")
);
--> statement-breakpoint
CREATE TABLE "election" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"created_by" uuid NOT NULL,
	"source" "election_source" DEFAULT 'user' NOT NULL,
	"external_id" text,
	"source_url" text,
	"source_data" jsonb,
	"title" text NOT NULL,
	"summary" text NOT NULL,
	"description" text,
	"ballot_type" "ballot_type" DEFAULT 'single_choice' NOT NULL,
	"status" "election_status" DEFAULT 'draft' NOT NULL,
	"jurisdiction" text,
	"election_date" date,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "election_source_external_id_unique" UNIQUE("source","external_id")
);
--> statement-breakpoint
ALTER TABLE "election_option" ADD CONSTRAINT "election_option_election_id_election_id_fk" FOREIGN KEY ("election_id") REFERENCES "public"."election"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "election_topic" ADD CONSTRAINT "election_topic_election_id_election_id_fk" FOREIGN KEY ("election_id") REFERENCES "public"."election"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "election_topic" ADD CONSTRAINT "election_topic_domain_id_domain_id_fk" FOREIGN KEY ("domain_id") REFERENCES "public"."domain"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "election_topic" ADD CONSTRAINT "election_topic_program_id_program_id_fk" FOREIGN KEY ("program_id") REFERENCES "public"."program"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "election" ADD CONSTRAINT "election_created_by_app_user_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."app_user"("id") ON DELETE restrict ON UPDATE no action;