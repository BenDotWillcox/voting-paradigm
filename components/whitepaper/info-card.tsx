
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

type InfoCardProps = {
	icon: LucideIcon;
	title: string;
	description: string;
	className?: string;
};

export function InfoCard({
	icon: Icon,
	title,
	description,
	className,
}: InfoCardProps) {
	return (
		<Card className={cn("flex flex-col", className)}>
			<CardHeader>
				<div className="mb-4 flex justify-center">
					<div className="rounded-full bg-primary/10 p-4">
						<Icon className="size-8 text-primary" />
					</div>
				</div>
				<CardTitle className="text-center text-xl font-semibold">
					{title}
				</CardTitle>
			</CardHeader>
			<CardContent className="flex-grow">
				<p className="text-center text-muted-foreground">{description}</p>
			</CardContent>
		</Card>
	);
}


