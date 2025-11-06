import { ProposalForm } from "@/components/forms/proposal-form";

export default function CreateProposalPage() {
  return (
    <div className="container mx-auto py-8 max-w-4xl">
      <h1 className="text-3xl font-bold mb-8">Create Proposal</h1>
      <ProposalForm />
    </div>
  );
}
