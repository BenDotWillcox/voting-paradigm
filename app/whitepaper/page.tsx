
import { Button } from "@/components/ui/button";
import { InfoCard } from "@/components/whitepaper/info-card";
import {
	Badge,
	Book,
	BrainCircuit,
	Database,
	Download,
	File,
	FileText,
	GitFork,
	Globe,
	Lock,
	Map,
	Network,
	Shield,
	Signal,
	User,
	Users,
	Vote,
} from "lucide-react";

export default function WhitepaperPage() {
	return (
		<div className="container mx-auto px-4 py-12">
			<div className="prose max-w-none text-left">
				<h1 className="text-3xl font-bold mb-3 leading-relaxed text-center">
					<strong>
						Subsidiarity-First Liquid Democracy with Personal AI Agents: A
						Secure, Auditable, and Privacy-Preserving Civic System
					</strong>
				</h1>

				<div className="flex justify-center my-8">
					<Button>
						<Download className="mr-2 size-4" />
						Download Whitepaper
					</Button>
				</div>

				<div>
					<h3 className="text-xl font-semibold mb-2 mt-4 text-center">
						Abstract
					</h3>
					<p className="mx-auto mb-3 max-w-4xl leading-relaxed">
						We propose a digital civic system that combines topic-scoped liquid
						delegation, personal AI voting agents, and cryptographic privacy to
						overcome structural limitations of contemporary representative
						democracy. The design aims to (1) reduce ideological distortion
						from two-party dynamics, (2) align outcomes with heterogeneous
						citizen preferences, (3) push decisions to the lowest competent
						jurisdiction (subsidiarity), and (4) maximize transparency without
						compromising ballot secrecy. We specify identity, voting,
						delegation, and jurisdiction components; describe protocols for
						proposal intake, validation, and voting; and outline threat models,
						safety mitigations, and a phased adoption roadmap.
					</p>
				</div>
			</div>

			<div>
				<h3 className="text-2xl font-semibold mb-4 mt-8 text-center">
					Problem Statement
				</h3>
				<p className="mx-auto mb-6 max-w-4xl text-center leading-relaxed">
					Contemporary representative democracies face structural challenges:
					voting systems often amplify polarization and waste votes, large
					constituencies lead to a representation gap, decision-making is
					frequently over-centralized, and a lack of transparency hinders
					accountability.
				</p>
				<div className="grid grid-cols-1 md:grid-cols-2 gap-6">
					<InfoCard
						icon={Vote}
						title="Polarization & Wasted Votes"
						description="First-past-the-post magnifies extremes and discourages moderate/third-option support."
					/>
					<InfoCard
						icon={Users}
						title="Representation Gap"
						description="A U.S. House member represents ~770,000 constituents—too coarse to reflect preference diversity."
					/>
					<InfoCard
						icon={Globe}
						title="Over-centralization"
						description="Policy is often set at levels too distant from the problem's locus."
					/>
					<InfoCard
						icon={Shield}
						title="Opaque Accountability"
						description="Limited access to process/records hinders informed consent and fair credit/blame."
					/>
				</div>
			</div>

			<div>
				<h3 className="text-2xl font-semibold mb-4 mt-8 text-center">
					Why Now
				</h3>
				<p className="mx-auto mb-6 max-w-4xl text-center leading-relaxed">
					Recent advances in internet connectivity, artificial intelligence,
					and cryptography now make it possible to build a more direct, secure,
					and responsive democratic system.
				</p>
				<div className="grid grid-cols-1 md:grid-cols-3 gap-6">
					<InfoCard
						icon={Signal}
						title="Information Exchange"
						description="Widespread internet access enables large-scale public discussion."
					/>
					<InfoCard
						icon={BrainCircuit}
						title="AI Advances"
						description="Preference modeling, natural-language alignment, and agentic assistance support 'always-represented' citizens with opt-in automation."
					/>
					<InfoCard
						icon={Lock}
						title="Modern Cryptography"
						description="Verifiable yet private eligibility and auditable tallies are feasible with threshold cryptography, MPC, and zero-knowledge proofs."
					/>
				</div>
			</div>

			<div>
				<h3 className="text-2xl font-semibold mb-4 mt-8 text-center">
					System Overview
				</h3>
				<p className="mb-3 leading-relaxed">
					<strong>High-level flow:</strong>
				</p>
				<ol className="mb-3 ml-4">
					<li className="mb-1">Citizens onboard with privacy-preserving proof of eligibility.</li>
					<li className="mb-1">Proposals pass automated and human validation.</li>
					<li className="mb-1">The jurisdiction function assigns eligible voters with impact weights (if used).</li>
					<li className="mb-1">Citizens vote directly, delegate per topic, or allow their AI agent to cast votes within user-set confidence thresholds.</li>
					<li className="mb-1">Votes are tallied with public verifiability and private ballot secrecy.</li>
					<li className="mb-1">
						Results, rationales, and implementation metrics are published.
					</li>
				</ol>
				<h4 className="text-xl font-semibold mb-4 mt-6 text-center">
					Actors
				</h4>
				<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
					<InfoCard
						icon={User}
						title="Citizens"
						description="Participants who can vote, delegate, or create proposals."
					/>
					<InfoCard
						icon={Users}
						title="Delegates"
						description="Trusted individuals voting on behalf of citizens on specific topics."
					/>
					<InfoCard
						icon={FileText}
						title="Proposal Authors"
						description="Individuals or groups who draft and submit policy proposals."
					/>
					<InfoCard
						icon={Network}
						title="Validation Agents"
						description="Automated or human agents who check proposals against validation criteria."
					/>
					<InfoCard
						icon={Shield}
						title="Governance Stewards"
						description="Overseers of the system's health, parameters, and upgrade processes."
					/>
				</div>
				<h4 className="text-xl font-semibold mb-4 mt-6 text-center">
					Artifacts
				</h4>
				<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
					<InfoCard
						icon={Badge}
						title="Identity Credentials"
						description="Secure, private, and verifiable digital credentials for proving eligibility."
					/>
					<InfoCard
						icon={GitFork}
						title="Delegation Graph"
						description="A public map of all delegation relationships, showing trust flows."
					/>
					<InfoCard
						icon={Book}
						title="Policy Ontology"
						description="A structured vocabulary for categorizing proposals and delegations."
					/>
					<InfoCard
						icon={Map}
						title="Jurisdiction Map"
						description="Defines the scope of impact and eligible voters for any given proposal."
					/>
					<InfoCard
						icon={File}
						title="Ballot Registry"
						description="A record of all past, present, and future ballots."
					/>
					<InfoCard
						icon={Database}
						title="Ledger"
						description="A verifiable log for all governance actions and outcomes."
					/>
				</div>
			</div>

			<div className="prose max-w-none text-left">
				<h3 className="text-xl font-semibold mb-2 mt-4">4. Core Components</h3>

				<h4 className="text-lg font-semibold mb-2 mt-3">
					4.1 Identity & Eligibility
				</h4>
				<ul className="mb-3">
					<li className="mb-1 ml-4">Multi-issuer verifiable credentials; proof of uniqueness; revocation & recovery.</li>
					<li className="mb-1 ml-4">zk-proof of eligibility to vote without revealing identity (&quot;I&apos;m eligible &amp; haven&apos;t voted in this ballot&quot;).</li>
				</ul>

				<h4 className="text-lg font-semibold mb-2 mt-3">
					4.2 Delegation Graph
				</h4>
				<ul className="mb-3">
					<li className="mb-1 ml-4">Topic-scoped delegations with optional time-decay and inbound caps.</li>
					<li className="mb-1 ml-4">Delegation transparency in aggregate (expose concentration indices, not who delegated to whom).</li>
				</ul>

				<h4 className="text-lg font-semibold mb-2 mt-3">
					4.3 Jurisdiction Resolver
				</h4>
				<ul className="mb-3">
					<li className="mb-1 ml-4">Public, deterministic function: <code>w = f(distance, exposure, stake, population)</code>.</li>
					<li className="mb-1 ml-4">Sandbox explorer to simulate parameter impacts; appeals & review process.</li>
				</ul>

				<h4 className="text-lg font-semibold mb-2 mt-3">
					4.4 AI Voting Agent
				</h4>
				<ul className="mb-3">
					<li className="mb-1 ml-4">Local preference store; explainable inferences; user-defined confidence threshold; pre-commit intent notifications; easy override and per-topic off-switch.</li>
					<li className="mb-1 ml-4">Signed model versions; audit trails; bias and robustness testing.</li>
				</ul>

				<h4 className="text-lg font-semibold mb-2 mt-3">
					4.5 Ledger & Data Plane
				</h4>
				<ul className="mb-3">
					<li className="mb-1 ml-4">Off-chain private ballots with on-chain commitments (or rollups).</li>
					<li className="mb-1 ml-4">Public, append-only logs for proposals, parameters, model versions, and aggregate outcomes.</li>
				</ul>

				<h3 className="text-xl font-semibold mb-2 mt-4">5. Protocols</h3>

				<h4 className="text-lg font-semibold mb-2 mt-3">
					5.1 Onboarding
				</h4>
				<ol className="mb-3 ml-4">
					<li className="mb-1">Collect/verify credentials from approved issuers.</li>
					<li className="mb-1">Run uniqueness + liveness ceremony.</li>
					<li className="mb-1">Issue zk-eligible credential; set recovery contacts/flows.</li>
				</ol>

				<h4 className="text-lg font-semibold mb-2 mt-3">
					5.2 Proposal Lifecycle
				</h4>
				<ul className="mb-3">
					<li className="mb-1 ml-4">Submit → Validate → Diagnose/Revise → Jurisdiction Assignment → Ballot Scheduling.</li>
					<li className="mb-1 ml-4">Automated checks: semantic dedupe, budget sanity, legal feasibility, implementation readiness, and equity/impact analysis.</li>
					<li className="mb-1 ml-4">Diagnostic report with remediation guidance if rejected.</li>
				</ul>

				<h4 className="text-lg font-semibold mb-2 mt-3">
					5.3 Voting Lifecycle
				</h4>
				<ol className="mb-3 ml-4">
					<li className="mb-1">Ballot opens → notifications (direct, delegate, agent-intent).</li>
					<li className="mb-1">Citizen can vote, delegate, or allow agent.</li>
					<li className="mb-1">Ballots executed via coercion-resistant protocol; public verifiable tally proofs; post-vote transparency report.</li>
				</ol>

				<h3 className="text-xl font-semibold mb-2 mt-4">6. Security, Privacy, and Threat Model</h3>
				<p className="mb-3 leading-relaxed">
					<strong>Adversaries:</strong> Sybil attackers, vote buyers, coercers, spam submitters, insiders, model poisoners.
				</p>
				<p className="mb-3 leading-relaxed">
					<strong>Mitigations:</strong> zk-eligibility, mixnets/threshold cryptography, no provable receipts, delegation caps/decay, rate limits, adversarial ML defenses, secure enclaves or MPC for sensitive inference, incident response playbooks.
				</p>

				<h3 className="text-xl font-semibold mb-2 mt-4">7. Governance & Upgrades</h3>
				<ul className="mb-3">
					<li className="mb-1 ml-4">Two-tier: (a) constitutional layer with slow-changing principles; (b) parametric layer (jurisdiction weights, delegation caps) with faster but still auditable change.</li>
					<li className="mb-1 ml-4">Signed releases, migration plans, and rollback procedures.</li>
				</ul>

				<h3 className="text-xl font-semibold mb-2 mt-4">8. Ethics & Equity</h3>
				<ul className="mb-3">
					<li className="mb-1 ml-4">Accessibility (language, disability support, offline kiosks).</li>
					<li className="mb-1 ml-4">Differential privacy for analytics.</li>
					<li className="mb-1 ml-4">Fairness audits of agents and proposal pipeline.</li>
					<li className="mb-1 ml-4">Clear consent boundaries and data minimization.</li>
				</ul>

				<h3 className="text-xl font-semibold mb-2 mt-4">9. Implementation Roadmap</h3>
				<ul className="mb-3">
					<li className="mb-1 ml-4"><strong>Phase 0 (MVP):</strong> Advisory votes in a voluntary association; direct + delegation, no agents; publish dashboards.</li>
					<li className="mb-1 ml-4"><strong>Phase 1:</strong> Add AI agents (opt-in), explainability, and preview-intent; launch policy pipeline.</li>
					<li className="mb-1 ml-4"><strong>Phase 2:</strong> Municipal pilot with limited binding scopes (e.g., participatory budgeting).</li>
					<li className="mb-1 ml-4"><strong>Phase 3:</strong> Inter-jurisdictional issues with the resolver; external audits; formal verification of critical contracts.</li>
				</ul>

				<h3 className="text-xl font-semibold mb-2 mt-4">10. Metrics & Evaluation</h3>
				<p className="mb-3 leading-relaxed">
					Turnout; active delegation rate; concentration index; proposal pass-through; time-to-policy; reversal rates; satisfaction surveys; equality of participation; error budgets for outages.
				</p>

				<h3 className="text-xl font-semibold mb-2 mt-4">11. Open Questions</h3>
				<ul className="mb-3">
					<li className="mb-1 ml-4">Best coercion-resistant scheme under cost constraints?</li>
					<li className="mb-1 ml-4">Jurisdiction function parameters for environmental externalities?</li>
					<li className="mb-1 ml-4">How to balance transparency with anonymity for delegates?</li>
					<li className="mb-1 ml-4">Agent liability: when an automated vote demonstrably misrepresents user intent.</li>
				</ul>

				<h3 className="text-xl font-semibold mb-2 mt-4">12. Conclusion</h3>
				<p className="mb-3 leading-relaxed">
					A subsidiarity-first, AI-assisted liquid democracy—secured by modern
					cryptography—can increase fidelity, locality, and accountability. The
					phased plan and safety guardrails aim to make this both practical and
					trustworthy.
				</p>
			</div>
		</div>
	);
}
