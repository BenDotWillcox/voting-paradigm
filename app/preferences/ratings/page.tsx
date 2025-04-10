// app/preferences/ratings/page.tsx
import { PreferencesForm } from "@/components/forms/preferences-form";
import { getUserPreferencesByUserIdAction } from "@/actions/user_preferences-actions";
import { auth } from "@clerk/nextjs/server";

export default async function RatingsPage() {
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
        Move the sliders to indicate your preference between different political positions. 
        Your scores will help match you with candidates that share your values.
      </p>
      <div className="flex justify-center">
        <PreferencesForm initialValues={preferences} userId={userId} />
      </div>
    </div>
  );
}