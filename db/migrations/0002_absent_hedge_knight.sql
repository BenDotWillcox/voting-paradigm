CREATE TYPE "public"."preference_session_status" AS ENUM('active', 'completed', 'abandoned');--> statement-breakpoint
CREATE TABLE "preference_response" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"session_id" uuid NOT NULL,
	"question_id" text NOT NULL,
	"question_type" text NOT NULL,
	"question_prompt" text NOT NULL,
	"options_json" jsonb NOT NULL,
	"chosen_option_id" text NOT NULL,
	"strength" numeric(4, 1),
	"response_time_ms" integer,
	"ordinal" integer NOT NULL,
	"source" text DEFAULT 'bank' NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "preference_session" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" uuid NOT NULL,
	"status" "preference_session_status" DEFAULT 'active' NOT NULL,
	"model_version" text DEFAULT 'thurstone_v1' NOT NULL,
	"state_snapshot" jsonb NOT NULL,
	"target_questions" integer DEFAULT 25 NOT NULL,
	"n_questions" integer DEFAULT 0 NOT NULL,
	"current_question" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "preference_response" ADD CONSTRAINT "preference_response_session_id_preference_session_id_fk" FOREIGN KEY ("session_id") REFERENCES "public"."preference_session"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "preference_session" ADD CONSTRAINT "preference_session_user_id_app_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."app_user"("id") ON DELETE cascade ON UPDATE no action;