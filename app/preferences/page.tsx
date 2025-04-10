// app/preferences/page.tsx
import { redirect } from "next/navigation";

export default function PreferencesPage() {
  redirect("/preferences/ratings");
}