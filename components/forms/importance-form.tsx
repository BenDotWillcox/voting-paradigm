"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { setUserPreferencesAction } from "@/actions/user_preferences-actions";
import { toast } from "sonner";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import { Check, Loader2, GripVertical, LayoutGrid, Plus, Trash2, PlusCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { useAutoAnimate } from "@formkit/auto-animate/react";

const POLITICAL_AXES = [
  {
    id: "federalVsUnitary",
    title: "Government Structure",
    description: "Federal vs Unitary systems",
  },
  {
    id: "democraticVsAuthoritarian",
    title: "Governance Style",
    description: "Democratic vs Authoritarian approaches",
  },
  {
    id: "globalistVsIsolationist",
    title: "International Relations",
    description: "Globalist vs Isolationist policies",
  },
  {
    id: "militaristVsPacifist",
    title: "Defense Policy",
    description: "Militarist vs Pacifist approaches",
  },
  {
    id: "securityVsFreedom",
    title: "Liberty vs Security",
    description: "Security measures vs Personal freedom",
  },
  {
    id: "equalityVsMarkets",
    title: "Economic System",
    description: "Economic equality vs Free markets",
  },
  {
    id: "secularVsReligious",
    title: "Role of Religion",
    description: "Secular vs Religious governance",
  },
  {
    id: "progressiveVsTraditional",
    title: "Social Values",
    description: "Progressive vs Traditional values",
  },
  {
    id: "assimilationistVsMulticulturalist",
    title: "Cultural Integration",
    description: "Assimilation vs Multiculturalism",
  },
];

// Colors for tier markers
const TIER_COLORS = [
  "bg-red-500", "bg-orange-500", "bg-yellow-500", "bg-green-500", 
  "bg-blue-500", "bg-indigo-500", "bg-purple-500", "bg-pink-500"
];

// Generate a unique ID for new tiers
const generateTierId = () => `tier-${Date.now()}-${Math.floor(Math.random() * 1000)}`;

// Add this type definition after POLITICAL_AXES
interface PoliticalAxis {
  id: string;
  title: string;
  description: string;
}

interface Tier {
  id: string;
  name: string;
  items: PoliticalAxis[];
}

// Update these definitions
const initialTier: Tier = {
  id: "default-tier",
  name: "All Issues",
  items: [...POLITICAL_AXES],
};

const emptyStagingArea: Tier = {
  id: "unassigned",
  name: "Unassigned Issues",
  items: [],
};

export function ImportanceForm({
  initialValues = {},
  userId,
}: {
  initialValues?: any;
  userId: string;
}) {
  const [isLoading, setIsLoading] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [tiersParentRef] = useAutoAnimate();

  // Function to get weights based on tier position - higher tiers have higher weights
  const getWeightForTier = (tierIndex: number, totalTiers: number) => {
    // This creates a linear distribution from 2.0 (top tier) to 0.25 (bottom tier)
    if (totalTiers === 1) return 1; // If only one tier, use neutral weight
    return 2 - ((tierIndex / (totalTiers - 1)) * 1.75);
  };

  // Initialize with a default single tier containing all items
  const getInitialTiers = () => {
    // Default to a single tier with all items
    const initialTier: Tier = {
      id: "default-tier",
      name: "All Issues",
      items: [...POLITICAL_AXES],
    };

    const emptyStagingArea: Tier = {
      id: "unassigned",
      name: "Unassigned Issues",
      items: [],
    };

    let customTiers = [initialTier];

    // If we have existing weights, try to reconstruct the tiers
    if (initialValues?.axisImportance) {
      try {
        const importanceObj = typeof initialValues.axisImportance === 'string'
          ? JSON.parse(initialValues.axisImportance)
          : initialValues.axisImportance;

        // Create an ordered array of weights
        const uniqueWeights = [...new Set(Object.values(importanceObj))].sort((a: any, b: any) => b - a);
        
        // If we have weights, create a tier for each unique weight
        if (uniqueWeights.length > 0) {
          // Clear the default tier
          initialTier.items = [];
          customTiers = uniqueWeights.map((weight, index) => {
            // Create a tier for this weight
            const tier: Tier = {
              id: `tier-${index}`,
              name: index === 0 ? "Highest Priority" : 
                    index === uniqueWeights.length - 1 ? "Lowest Priority" : 
                    `Priority ${index + 1}`,
              items: []
            };

            // Add items with this weight to this tier
            Object.entries(importanceObj).forEach(([id, itemWeight]) => {
              if (itemWeight === weight) {
                const item = POLITICAL_AXES.find(axis => axis.id === id);
                if (item) tier.items.push(item);
              }
            });

            return tier;
          });
        }

        // Check if any items aren't assigned to a tier
        const assignedItemIds = Object.keys(importanceObj);
        const unassignedItems = POLITICAL_AXES.filter(
          axis => !assignedItemIds.includes(axis.id)
        );

        // Add unassigned items to the unassigned tier
        if (unassignedItems.length > 0) {
          emptyStagingArea.items = unassignedItems;
        }
      } catch (e) {
        console.error("Error parsing importance weights", e);
      }
    }

    return [...customTiers, emptyStagingArea];
  };

  const [tiers, setTiers] = useState(getInitialTiers);

  // Add a new tier
  const addTier = () => {
    const newTier: Tier = {
      id: generateTierId(),
      name: `Priority ${tiers.length}`,
      items: []
    };

    // Insert new tier before the unassigned tier
    const updatedTiers = [...tiers.slice(0, -1), newTier, tiers[tiers.length - 1]];
    setTiers(updatedTiers);
  };

  // Remove a tier and move its items to unassigned
  const removeTier = (tierId: string) => {
    const tierIndex = tiers.findIndex(tier => tier.id === tierId);
    if (tierIndex === -1 || tierId === "unassigned") return;

    const updatedTiers = [...tiers];
    const itemsToMove = updatedTiers[tierIndex].items;
    
    // Remove the tier
    updatedTiers.splice(tierIndex, 1);
    
    // Move items to unassigned
    const unassignedIndex = updatedTiers.findIndex(tier => tier.id === "unassigned");
    if (unassignedIndex !== -1) {
      updatedTiers[unassignedIndex].items = [
        ...updatedTiers[unassignedIndex].items,
        ...itemsToMove
      ];
    }

    setTiers(updatedTiers);
  };

  // Update tier name
  const updateTierName = (tierId: string, name: string) => {
    setTiers(tiers.map(tier => 
      tier.id === tierId ? { ...tier, name } : tier
    ));
  };

  const handleDragEnd = (result: any) => {
    if (!result.destination) return;
    
    const { source, destination } = result;
    
    // Handle dragging items between tiers
    if (result.type === "item") {
      const sourceIndex = tiers.findIndex(tier => tier.id === source.droppableId);
      const destIndex = tiers.findIndex(tier => tier.id === destination.droppableId);
      
      if (sourceIndex === -1 || destIndex === -1) return;
      
      const updatedTiers = [...tiers];
      const [movedItem] = updatedTiers[sourceIndex].items.splice(source.index, 1);
      updatedTiers[destIndex].items.splice(destination.index, 0, movedItem);
      
      setTiers(updatedTiers);
    } 
    // Handle reordering tiers
    else if (result.type === "tier") {
      // Don't allow moving the unassigned tier
      if (source.index === tiers.length - 1 || destination.index === tiers.length - 1) return;
      
      const updatedTiers = [...tiers];
      const [movedTier] = updatedTiers.splice(source.index, 1);
      updatedTiers.splice(destination.index, 0, movedTier);
      
      setTiers(updatedTiers);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setIsSaved(false);
    
    try {
      // Create importance weights object based on tier position
      const importanceWeights: Record<string, number> = {};
      
      // Only process actual tiers (not the unassigned staging area)
      const actualTiers = tiers.filter(tier => tier.id !== "unassigned");
      
      // Assign weights based on tier position
      actualTiers.forEach((tier, tierIndex) => {
        const weight = getWeightForTier(tierIndex, actualTiers.length);
        
        tier.items.forEach(item => {
          if (item) {
            importanceWeights[item.id] = weight;
          }
        });
      });
      
      // Update preferences with new importance weights
      await setUserPreferencesAction({
        userId,
        axisImportance: importanceWeights,
        ...initialValues,
      });
      
      setIsSaved(true);
      toast.success("Priority tiers saved", {
        description: "Your issue priorities have been updated successfully.",
      });
    } catch (error) {
      toast.error("Failed to save priorities. Please try again.");
    } finally {
      setIsLoading(false);
      setTimeout(() => setIsSaved(false), 2000);
    }
  };

  return (
    <form className="w-full max-w-3xl" onSubmit={handleSubmit}>
      <div className="bg-card rounded-xl border shadow-sm p-6 mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">Priority Tiers</h2>
          <div className="text-sm text-muted-foreground flex items-center gap-2">
            <LayoutGrid className="h-4 w-4" />
            <span>Drag items between tiers</span>
          </div>
        </div>
        
        <div className="text-sm text-muted-foreground mb-6">
          <p>Create and arrange tiers to indicate importance. Higher tiers have more weight when calculating recommendations.</p>
        </div>
        
        <DragDropContext onDragEnd={handleDragEnd}>
          <Droppable droppableId="tiers-container" type="tier">
            {(provided) => (
              <div 
                ref={(el) => {
                  provided.innerRef(el);
                  // @ts-ignore - combining refs
                  if (tiersParentRef.current) tiersParentRef.current = el;
                }}
                {...provided.droppableProps}
                className="space-y-6"
              >
                {tiers.map((tier, tierIndex) => (
                  <Draggable 
                    key={tier.id} 
                    draggableId={tier.id} 
                    index={tierIndex}
                    isDragDisabled={tier.id === "unassigned"}
                  >
                    {(provided, snapshot) => (
                      <div
                        ref={provided.innerRef}
                        {...provided.draggableProps}
                        className={cn(
                          "space-y-2 rounded-lg transition-all",
                          snapshot.isDragging ? "opacity-75" : "",
                          tier.id === "unassigned" ? "mt-10" : ""
                        )}
                      >
                        <div className="flex items-center gap-2">
                          {tier.id !== "unassigned" && (
                            <div 
                              {...provided.dragHandleProps}
                              className="touch-none cursor-grab active:cursor-grabbing"
                            >
                              <GripVertical className="h-5 w-5 text-muted-foreground" />
                            </div>
                          )}
                          
                          <div className={cn(
                            "h-1.5 flex-1 rounded-full",
                            tier.id !== "unassigned" 
                              ? TIER_COLORS[tierIndex % TIER_COLORS.length]
                              : "bg-gray-300"
                          )} />
                          
                          {tier.id !== "unassigned" ? (
                            <Input
                              value={tier.name}
                              onChange={(e) => updateTierName(tier.id, e.target.value)}
                              className="h-8 w-40 text-sm font-medium"
                              aria-label="Tier name"
                            />
                          ) : (
                            <div className="font-medium">{tier.name}</div>
                          )}
                          
                          {tier.id !== "unassigned" && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => removeTier(tier.id)}
                              className="h-8 w-8 text-muted-foreground hover:text-destructive"
                              type="button"
                              aria-label="Remove tier"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                          
                          {tier.id !== "unassigned" && (
                            <div className="text-xs text-muted-foreground">
                              {(() => {
                                const actualTiers = tiers.filter(t => t.id !== "unassigned");
                                return tierIndex === 0 && actualTiers.length > 1 ? "(2.0x weight)" : 
                                  tiers.length === 2 ? "(1.0x weight)" : 
                                  tierIndex === tiers.length - 2 ? "(0.25x weight)" : 
                                  `(${getWeightForTier(tierIndex, tiers.length - 1).toFixed(2)}x weight)`;
                              })()}
                            </div>
                          )}
                        </div>
                        
                        <Droppable droppableId={tier.id} direction="horizontal" type="item">
                          {(provided) => (
                            <div
                              ref={provided.innerRef}
                              {...provided.droppableProps}
                              className={cn(
                                "min-h-20 rounded-lg border border-dashed p-3 flex flex-wrap gap-2",
                                tier.items.length === 0 ? "justify-center items-center" : ""
                              )}
                            >
                              {tier.items.length === 0 && (
                                <span className="text-sm text-muted-foreground">
                                  {tier.id === "unassigned" ? "All issues assigned" : "Drop issues here"}
                                </span>
                              )}
                              
                              {tier.items.map((item, index) => item && (
                                <Draggable key={item.id} draggableId={item.id} index={index}>
                                  {(provided, snapshot) => (
                                    <div
                                      ref={provided.innerRef}
                                      {...provided.draggableProps}
                                      className={cn(
                                        `rounded-lg border bg-card p-2 flex flex-col justify-between shadow-sm transition-shadow`,
                                        snapshot.isDragging ? "shadow-lg" : "",
                                        "w-[calc(50%-8px)]", // 2 items per row on mobile
                                        "sm:w-[calc(33.333%-8px)]", // 3 items per row on small screens
                                        "md:w-[calc(25%-8px)]", // 4 items per row on medium screens
                                      )}
                                    >
                                      <div className="flex items-start gap-2">
                                        <div
                                          {...provided.dragHandleProps}
                                          className="touch-none flex-shrink-0 p-1 rounded-md hover:bg-muted cursor-grab active:cursor-grabbing"
                                        >
                                          <GripVertical className="h-4 w-4 text-muted-foreground" />
                                        </div>
                                        <div>
                                          <div className="font-medium text-sm leading-tight">{item.title}</div>
                                          <div className="text-xs text-muted-foreground mt-1 leading-tight">
                                            {item.description}
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                  )}
                                </Draggable>
                              ))}
                              {provided.placeholder}
                            </div>
                          )}
                        </Droppable>
                      </div>
                    )}
                  </Draggable>
                ))}
                {provided.placeholder}
              </div>
            )}
          </Droppable>
        </DragDropContext>
        
        <div className="mt-6">
          <Button 
            type="button" 
            variant="outline" 
            size="sm"
            className="text-sm"
            onClick={addTier}
          >
            <PlusCircle className="h-4 w-4 mr-2" />
            Add New Tier
          </Button>
        </div>
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
            "Save Priority Tiers"
          )}
        </Button>
      </div>
    </form>
  );
} 