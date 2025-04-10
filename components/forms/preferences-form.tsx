// components/forms/preferences-form.tsx
"use client";

import { PreferenceSlider } from "@/components/ui/preference-slider";
import { Button } from "@/components/ui/button";
import { setUserPreferencesAction } from "@/actions/user_preferences-actions";
import { toast } from "sonner";
import { useState } from "react";
import { FlagTriangleRight, Building, Globe, Swords, Lock, 
         CircleDollarSign, BookOpen, Clock, Users, Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const PREFERENCES = [
  {
    key: "federalVsUnitary",
    title: "Government Structure",
    firstOption: "Federal",
    secondOption: "Unitary",
    firstIcon: <Building />,
    secondIcon: <FlagTriangleRight />,
    descriptions: {
      "-10": "Strongly favor federal systems with significant state/province autonomy",
      "-5": "Prefer federal systems with reasonable division of powers",
      "0": "Neutral on government structure",
      "5": "Prefer unitary systems with some local authority",
      "10": "Strongly favor centralized unitary government",
    }
  },
  {
    key: "democraticVsAuthoritarian",
    title: "Governance Style",
    firstOption: "Democratic",
    secondOption: "Authoritarian",
    firstIcon: <Users />,
    secondIcon: <FlagTriangleRight />,
    descriptions: {
      "-10": "Strongly favor direct democracy with maximum citizen participation",
      "-5": "Prefer representative democracy with strong citizen oversight",
      "0": "Balance between democratic and authoritarian elements",
      "5": "Prefer efficient government with limited democratic processes",
      "10": "Strongly favor decisive authoritarian governance",
    }
  },
  {
    key: "globalistVsIsolationist",
    title: "International Relations",
    firstOption: "Globalist",
    secondOption: "Isolationist",
    firstIcon: <Globe />,
    secondIcon: <Building />,
    descriptions: {
      "-10": "Strongly favor international integration and global governance",
      "-5": "Prefer international cooperation while maintaining sovereignty",
      "0": "Balance between international engagement and domestic focus",
      "5": "Prefer limited international engagement focused on national interest",
      "10": "Strongly favor minimal international engagement and self-reliance",
    }
  },
  {
    key: "militaristVsPacifist",
    title: "Defense Policy",
    firstOption: "Militarist",
    secondOption: "Pacifist",
    firstIcon: <Swords />,
    secondIcon: <FlagTriangleRight />,
    descriptions: {
      "-10": "Strongly favor military strength and readiness to use force",
      "-5": "Prefer strong defense with careful use of military power",
      "0": "Balance between military capability and peaceful resolution",
      "5": "Prefer diplomatic solutions with minimal military involvement",
      "10": "Strongly favor non-violent approaches and minimal military",
    }
  },
  {
    key: "securityVsFreedom",
    title: "Liberty vs Security",
    firstOption: "Security",
    secondOption: "Freedom",
    firstIcon: <Lock />,
    secondIcon: <FlagTriangleRight />,
    descriptions: {
      "-10": "Strongly favor security measures even at cost to civil liberties",
      "-5": "Prefer security with reasonable protections for rights",
      "0": "Balance between security needs and personal freedom",
      "5": "Prefer personal liberty with reasonable security measures",
      "10": "Strongly favor maximum personal freedom and minimal restrictions",
    }
  },
  {
    key: "equalityVsMarkets",
    title: "Economic System",
    firstOption: "Equality",
    secondOption: "Free Markets",
    firstIcon: <Users />,
    secondIcon: <CircleDollarSign />,
    descriptions: {
      "-10": "Strongly favor economic equality through redistribution",
      "-5": "Prefer regulated markets with social safety nets",
      "0": "Balance between market freedom and economic equality",
      "5": "Prefer free markets with limited government intervention",
      "10": "Strongly favor unfettered markets with minimal regulation",
    }
  },
  {
    key: "secularVsReligious",
    title: "Role of Religion",
    firstOption: "Secular",
    secondOption: "Religious",
    firstIcon: <Building />,
    secondIcon: <BookOpen />,
    descriptions: {
      "-10": "Strongly favor complete separation of religion and state",
      "-5": "Prefer secular governance with respect for religious values",
      "0": "Neutral on the role of religion in governance",
      "5": "Prefer recognition of religion's role in public life",
      "10": "Strongly favor religious principles in governance",
    }
  },
  {
    key: "progressiveVsTraditional",
    title: "Social Values",
    firstOption: "Progressive",
    secondOption: "Traditional",
    firstIcon: <Clock />,
    secondIcon: <BookOpen />,
    descriptions: {
      "-10": "Strongly favor rapid social change and new cultural norms",
      "-5": "Prefer gradual social progress while respecting some traditions",
      "0": "Balance between progress and traditional values",
      "5": "Prefer traditional social norms with limited change",
      "10": "Strongly favor preservation of traditional values and structures",
    }
  },
  {
    key: "assimilationistVsMulticulturalist",
    title: "Cultural Integration",
    firstOption: "Assimilationist",
    secondOption: "Multiculturalist",
    firstIcon: <Users />,
    secondIcon: <Globe />,
    descriptions: {
      "-10": "Strongly favor cultural assimilation into dominant culture",
      "-5": "Prefer integration while maintaining some cultural elements",
      "0": "Balance between integration and cultural preservation",
      "5": "Prefer multicultural society with shared civic values",
      "10": "Strongly favor preservation of distinct cultural identities",
    }
  },
];

export function PreferencesForm({ initialValues = {}, userId }: { initialValues?: any, userId: string }) {
  const [values, setValues] = useState({ ...initialValues, userId });
  const [isLoading, setIsLoading] = useState(false);
  const [isSaved, setIsSaved] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setIsSaved(false);
    
    try {
      await setUserPreferencesAction(values);
      setIsSaved(true);
      toast.success("Preferences saved", {
        description: "Your preferences have been updated successfully."
      });
    } catch (error) {
      toast.error("Failed to save preferences. Please try again.");
    } finally {
      setIsLoading(false);
      // Reset the saved indicator after 2 seconds
      setTimeout(() => setIsSaved(false), 2000);
    }
  };

  return (
    <form className="space-y-12 w-full max-w-3xl" onSubmit={handleSubmit}>
      <div className="grid gap-10">
        {PREFERENCES.map((pref) => (
          <PreferenceSlider
            key={pref.key}
            firstOption={pref.firstOption}
            secondOption={pref.secondOption}
            defaultValue={Number(values[pref.key]) || 0}
            onChange={(value) => setValues((prev: any) => ({ ...prev, [pref.key]: value }))}
            firstIcon={pref.firstIcon}
            secondIcon={pref.secondIcon}
            descriptions={pref.descriptions}
            firstColor={pref.key === "federalVsUnitary" ? "#3b82f6" : undefined}
            secondColor={pref.key === "federalVsUnitary" ? "#ef4444" : undefined}
            title={pref.title}
          />
        ))}
      </div>
      
      <div className="flex justify-center mt-8">
        <Button 
          type="submit" 
          size="lg" 
          className={cn(
            "px-8 transition-all duration-300",
            isSaved ? "bg-green-600 hover:bg-green-700" : ""
          )}
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Saving...
            </>
          ) : isSaved ? (
            <>
              <Check className="mr-2 h-4 w-4" />
              Saved!
            </>
          ) : (
            "Save Preferences"
          )}
        </Button>
      </div>
    </form>
  );
}