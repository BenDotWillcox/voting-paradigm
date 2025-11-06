"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Plus, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { proposalFormSchema, type ProposalFormData } from "@/lib/validations/proposal-schema";
import { createProposalFormAction } from "@/actions/proposals-actions";
import { getAllDomainsAction, getProgramsByDomainAction } from "@/actions/topics-actions";
import { getAllUsersAction } from "@/actions/users-actions";
import { toast } from "sonner";

interface ProposalFormProps {
  defaultAuthorId?: string;
}

export function ProposalForm({ defaultAuthorId }: ProposalFormProps) {
  const router = useRouter();
  const [domains, setDomains] = useState<Array<{ id: string; name: string }>>([]);
  const [users, setUsers] = useState<Array<{ id: string; handle: string }>>([]);
  const [programsByDomain, setProgramsByDomain] = useState<Record<string, Array<{ id: string; name: string }>>>({});
  const [loading, setLoading] = useState(false);

  const form = useForm<ProposalFormData>({
    resolver: zodResolver(proposalFormSchema),
    defaultValues: {
      title: "",
      summary: "",
      problemPlain: "",
      implementingOrg: "",
      actions: [{ text: "" }, { text: "" }, { text: "" }],
      metrics: [{ name: "", unit: "", baselineVal: "", targetVal: "", deadline: "" }],
      topics: [{ domainId: "", isPrimary: true }],
      budgetItems: [{ itemName: "", oneTimeUsd: 0, annualUsd: 0, confidence: 0.5 }],
      fundingNotes: "",
      legalCitation: "",
      needsNewAuthority: false,
      equityBeneficiaries: "",
      equityCostBearers: "",
      safeguardsRollbackTrigger: "",
      safeguardsRollbackSteps: "",
      sunsetDate: "",
      privacyNotes: "",
      retentionDays: undefined,
      authorId: defaultAuthorId || "",
    },
  });

  useEffect(() => {
    const loadData = async () => {
      const [domainsRes, usersRes] = await Promise.all([
        getAllDomainsAction(),
        getAllUsersAction(),
      ]);
      if (domainsRes.isSuccess && domainsRes.data) {
        setDomains(domainsRes.data);
      }
      if (usersRes.isSuccess && usersRes.data) {
        setUsers(usersRes.data);
      }
    };
    loadData();
  }, []);

  const onSubmit = async (data: ProposalFormData) => {
    setLoading(true);
    try {
      const result = await createProposalFormAction(data);
      if (result.isSuccess && result.data) {
        toast.success(result.message);
        router.push(`/proposals/${result.data.id}`);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error("Failed to create proposal");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-8">
        {/* Header */}
        <Card>
          <CardHeader>
            <CardTitle>Header</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Title *</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Proposal title (≤60 chars)"
                      maxLength={60}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    {field.value?.length || 0}/60 characters
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="summary"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Summary *</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Brief summary (≤280 chars)"
                      maxLength={280}
                      rows={3}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    {field.value?.length || 0}/280 characters
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        {/* Essentials */}
        <Card>
          <CardHeader>
            <CardTitle>Essentials</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <FormField
              control={form.control}
              name="problemPlain"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Problem Description *</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Describe the problem (≤~250 words)"
                      maxLength={1500}
                      rows={6}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    {field.value?.length || 0}/1500 characters
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="implementingOrg"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Implementing Organization</FormLabel>
                  <FormControl>
                    <Input placeholder="Organization name" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Actions */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <FormLabel>Actions * (3-7, verb-first)</FormLabel>
                {form.watch("actions").length < 7 && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const current = form.getValues("actions");
                      form.setValue("actions", [...current, { text: "" }]);
                    }}
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Add Action
                  </Button>
                )}
              </div>
              {form.watch("actions").map((_, index) => (
                <FormField
                  key={index}
                  control={form.control}
                  name={`actions.${index}.text`}
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <div className="flex gap-2">
                          <Input
                            placeholder={`Action ${index + 1}`}
                            {...field}
                          />
                          {form.watch("actions").length > 3 && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => {
                                const current = form.getValues("actions");
                                form.setValue(
                                  "actions",
                                  current.filter((_, i) => i !== index)
                                );
                              }}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              ))}
            </div>

            {/* Metrics */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <FormLabel>Metrics * (SMART)</FormLabel>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const current = form.getValues("metrics");
                    form.setValue("metrics", [
                      ...current,
                      { name: "", unit: "", baselineVal: "", targetVal: "", deadline: "" },
                    ]);
                  }}
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Metric
                </Button>
              </div>
              {form.watch("metrics").map((_, index) => (
                <Card key={index}>
                  <CardContent className="pt-6 space-y-4">
                    <div className="flex items-center justify-between">
                      <FormLabel>Metric {index + 1}</FormLabel>
                      {form.watch("metrics").length > 1 && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => {
                            const current = form.getValues("metrics");
                            form.setValue(
                              "metrics",
                              current.filter((_, i) => i !== index)
                            );
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <FormField
                        control={form.control}
                        name={`metrics.${index}.name`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Name *</FormLabel>
                            <FormControl>
                              <Input placeholder="Metric name" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`metrics.${index}.unit`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Unit *</FormLabel>
                            <FormControl>
                              <Input placeholder="e.g., %, count, $" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                      <FormField
                        control={form.control}
                        name={`metrics.${index}.baselineVal`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Baseline Value *</FormLabel>
                            <FormControl>
                              <Input placeholder="0" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`metrics.${index}.baselineYear`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Baseline Year</FormLabel>
                            <FormControl>
                              <Input
                                type="number"
                                placeholder="2024"
                                {...field}
                                onChange={(e) =>
                                  field.onChange(
                                    e.target.value ? parseInt(e.target.value) : undefined
                                  )
                                }
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`metrics.${index}.baselineSource`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Baseline Source</FormLabel>
                            <FormControl>
                              <Input placeholder="Data source" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <FormField
                        control={form.control}
                        name={`metrics.${index}.targetVal`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Target Value *</FormLabel>
                            <FormControl>
                              <Input placeholder="0" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`metrics.${index}.deadline`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Deadline *</FormLabel>
                            <FormControl>
                              <Input type="date" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Scope */}
        <Card>
          <CardHeader>
            <CardTitle>Scope (Optional)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <FormField
              control={form.control}
              name="scopeGeojson"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>GeoJSON</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder='{"type": "Feature", ...}'
                      rows={4}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="populationEstimate"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Population Estimate</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        placeholder="0"
                        {...field}
                        onChange={(e) =>
                          field.onChange(
                            e.target.value ? parseInt(e.target.value) : undefined
                          )
                        }
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="populationSource"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Population Source</FormLabel>
                    <FormControl>
                      <Input placeholder="Data source" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          </CardContent>
        </Card>

        {/* Topics */}
        <Card>
          <CardHeader>
            <CardTitle>Topics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {form.watch("topics").map((_, index) => (
              <div key={index} className="grid grid-cols-3 gap-4">
                <FormField
                  control={form.control}
                  name={`topics.${index}.domainId`}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Domain *</FormLabel>
                      <Select
                        onValueChange={(value) => {
                          field.onChange(value);
                          // Load programs for this domain
                          if (value && !programsByDomain[value]) {
                            getProgramsByDomainAction(value).then((programsRes) => {
                              if (programsRes.isSuccess && programsRes.data) {
                                setProgramsByDomain((prev) => ({
                                  ...prev,
                                  [value]: programsRes.data!,
                                }));
                              }
                            });
                          }
                          // Clear program when domain changes
                          form.setValue(`topics.${index}.programId`, undefined);
                        }}
                        value={field.value}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select domain" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {domains.map((domain) => (
                            <SelectItem key={domain.id} value={domain.id}>
                              {domain.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={`topics.${index}.programId`}
                  render={({ field }) => {
                    const domainId = form.watch(`topics.${index}.domainId`);
                    const programs = domainId ? programsByDomain[domainId] || [] : [];
                    
                    return (
                      <FormItem>
                        <FormLabel>Program (Optional)</FormLabel>
                        <Select
                          onValueChange={field.onChange}
                          value={field.value || ""}
                          disabled={!domainId}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder={domainId ? "Select program" : "Select domain first"} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {programs.map((program) => (
                              <SelectItem key={program.id} value={program.id}>
                                {program.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    );
                  }}
                />
                <div className="flex items-end gap-2">
                  <FormField
                    control={form.control}
                    name={`topics.${index}.isPrimary`}
                    render={({ field }) => (
                      <FormItem className="flex items-center gap-2">
                        <FormControl>
                          <Checkbox
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                        <FormLabel className="!mt-0">Primary</FormLabel>
                      </FormItem>
                    )}
                  />
                  {form.watch("topics").length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        const current = form.getValues("topics");
                        form.setValue(
                          "topics",
                          current.filter((_, i) => i !== index)
                        );
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                const current = form.getValues("topics");
                form.setValue("topics", [
                  ...current,
                  { domainId: "", isPrimary: false },
                ]);
              }}
            >
              <Plus className="h-4 w-4 mr-1" />
              Add Topic
            </Button>
          </CardContent>
        </Card>

        {/* Budget */}
        <Card>
          <CardHeader>
            <CardTitle>Budget</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {form.watch("budgetItems").map((_, index) => (
              <Card key={index}>
                <CardContent className="pt-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <FormLabel>Budget Item {index + 1}</FormLabel>
                    {form.watch("budgetItems").length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => {
                          const current = form.getValues("budgetItems");
                          form.setValue(
                            "budgetItems",
                            current.filter((_, i) => i !== index)
                          );
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                  <FormField
                    control={form.control}
                    name={`budgetItems.${index}.itemName`}
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Item Name *</FormLabel>
                        <FormControl>
                          <Input placeholder="Budget item name" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <div className="grid grid-cols-3 gap-4">
                    <FormField
                      control={form.control}
                      name={`budgetItems.${index}.oneTimeUsd`}
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>One-time ($)</FormLabel>
                          <FormControl>
                            <Input
                              type="number"
                              placeholder="0"
                              {...field}
                              onChange={(e) =>
                                field.onChange(parseInt(e.target.value) || 0)
                              }
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name={`budgetItems.${index}.annualUsd`}
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Annual ($)</FormLabel>
                          <FormControl>
                            <Input
                              type="number"
                              placeholder="0"
                              {...field}
                              onChange={(e) =>
                                field.onChange(parseInt(e.target.value) || 0)
                              }
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name={`budgetItems.${index}.confidence`}
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Confidence (0-1)</FormLabel>
                          <FormControl>
                            <Input
                              type="number"
                              step="0.01"
                              min="0"
                              max="1"
                              placeholder="0.5"
                              {...field}
                              onChange={(e) =>
                                field.onChange(parseFloat(e.target.value) || 0.5)
                              }
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </CardContent>
              </Card>
            ))}
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                const current = form.getValues("budgetItems");
                form.setValue("budgetItems", [
                  ...current,
                  { itemName: "", oneTimeUsd: 0, annualUsd: 0, confidence: 0.5 },
                ]);
              }}
            >
              <Plus className="h-4 w-4 mr-1" />
              Add Budget Item
            </Button>
            <FormField
              control={form.control}
              name="fundingNotes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Funding Notes</FormLabel>
                  <FormControl>
                    <Textarea placeholder="Additional funding details" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        {/* Governance */}
        <Card>
          <CardHeader>
            <CardTitle>Governance</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <FormField
              control={form.control}
              name="legalCitation"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Legal Citation</FormLabel>
                  <FormControl>
                    <Input placeholder="Legal reference" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="needsNewAuthority"
              render={({ field }) => (
                <FormItem className="flex items-center gap-2">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <FormLabel className="!mt-0">Needs New Authority</FormLabel>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="equityBeneficiaries"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Equity Beneficiaries</FormLabel>
                  <FormControl>
                    <Textarea placeholder="Who benefits?" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="equityCostBearers"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Equity Cost Bearers</FormLabel>
                  <FormControl>
                    <Textarea placeholder="Who bears the costs?" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="safeguardsRollbackTrigger"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Rollback Trigger</FormLabel>
                  <FormControl>
                    <Textarea placeholder="Conditions for rollback" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="safeguardsRollbackSteps"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Rollback Steps</FormLabel>
                  <FormControl>
                    <Textarea placeholder="Steps to rollback" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="sunsetDate"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Sunset Date</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="retentionDays"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Retention Days</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        placeholder="Days"
                        {...field}
                        onChange={(e) =>
                          field.onChange(
                            e.target.value ? parseInt(e.target.value) : undefined
                          )
                        }
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="privacyNotes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Privacy Notes</FormLabel>
                  <FormControl>
                    <Textarea placeholder="Privacy considerations" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        {/* Author */}
        <Card>
          <CardHeader>
            <CardTitle>Author</CardTitle>
          </CardHeader>
          <CardContent>
            <FormField
              control={form.control}
              name="authorId"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Author *</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select author" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {users.map((user) => (
                        <SelectItem key={user.id} value={user.id}>
                          {user.handle}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        {/* Submit */}
        <div className="flex justify-end gap-4">
          <Button type="button" variant="outline" onClick={() => router.back()}>
            Cancel
          </Button>
          <Button type="submit" disabled={loading}>
            {loading ? "Creating..." : "Create Proposal"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
