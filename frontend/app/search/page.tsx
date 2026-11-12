"use client";

import { useState } from "react";
import { JobList } from "@/components/job-list";
import { PageHeader } from "@/components/page-header";
import { SearchForm } from "@/components/search-form";

export default function SearchPage() {
  const [refresh, setRefresh] = useState(0);
  return (
    <div>
      <PageHeader title="Search" description="Find practices in the NPI Registry. A repeat search continues after the leads you already fetched." />
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,34rem)_minmax(0,1fr)]">
        <section aria-labelledby="new-search" className="rounded-lg border bg-card p-5">
          <h2 id="new-search" className="mb-4 text-base font-semibold">
            New search
          </h2>
          <SearchForm onCreated={() => setRefresh((n) => n + 1)} />
        </section>
        <section aria-labelledby="searches">
          <h2 id="searches" className="mb-4 text-base font-semibold">
            Searches
          </h2>
          <JobList refreshKey={refresh} />
        </section>
      </div>
    </div>
  );
}
