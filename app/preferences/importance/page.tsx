import { ImportanceForm } from "@/components/forms/importance-form";
import { getUserPreferencesByUserIdAction } from "@/actions/user_preferences-actions";
import { auth } from "@clerk/nextjs/server";

export default async function ImportancePage() {
  const { userId } = await auth();
  
  // userId will never be null here because we check in the layout
  // but TypeScript doesn't know that
  if (!userId) {
    return null;
  }
  
  const { data: preferences } = await getUserPreferencesByUserIdAction(userId);

  return (
    <div>
      <p className="text-center text-muted-foreground mb-10">
        Place political issues in different priority tiers based on their importance to you.
        Critical issues will have twice the weight of moderate issues when calculating voting recommendations.
      </p>
      <div className="flex justify-center">
        <ImportanceForm initialValues={preferences} userId={userId} />
      </div>
    </div>
  );
} 