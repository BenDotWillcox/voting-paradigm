import { BallotCreationForm } from "@/components/forms/ballot-creation-form";

export default function CreateBallotPage() {
  return (
    <div className="container mx-auto max-w-4xl py-8">
      <h1 className="mb-2 text-3xl font-bold">Create Ballot-Based Election</h1>
      <p className="mb-8 text-muted-foreground">
        Configure election inputs from the constraints of a selected ballot type.
      </p>
      <BallotCreationForm />
    </div>
  );
}
