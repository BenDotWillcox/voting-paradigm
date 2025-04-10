CREATE TABLE "user_preferences" (
	"user_id" text PRIMARY KEY NOT NULL,
	"federal_vs_unitary" numeric DEFAULT '0' NOT NULL,
	"democratic_vs_authoritarian" numeric DEFAULT '0' NOT NULL,
	"globalist_vs_isolationist" numeric DEFAULT '0' NOT NULL,
	"militarist_vs_pacifist" numeric DEFAULT '0' NOT NULL,
	"security_vs_freedom" numeric DEFAULT '0' NOT NULL,
	"equality_vs_markets" numeric DEFAULT '0' NOT NULL,
	"secular_vs_religious" numeric DEFAULT '0' NOT NULL,
	"progressive_vs_traditional" numeric DEFAULT '0' NOT NULL,
	"assimilationist_vs_multiculturalist" numeric DEFAULT '0' NOT NULL,
	"additional_topics" json,
	"axis_importance" json,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "user_preferences" ADD CONSTRAINT "user_preferences_user_id_profiles_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("user_id") ON DELETE no action ON UPDATE no action;