"use client";

import { useState } from "react";
import { JobList } from "@/components/job-list";
import { SearchForm } from "@/components/search-form";

export default function SearchPage() {
  const [refresh, setRefresh] = useState(0);
  return (
    <div className="space-y-10">
      <section aria-labelledby="new-search">
        <h1 id="new-search" className="mb-4 text-xl font-semibold">
          New search
        </h1>
        <SearchForm onCreated={() => setRefresh((n) => n + 1)} />
      </section>
      <section aria-labelledby="searches">
        <h2 id="searches" className="mb-4 text-lg font-semibold">
          Searches
        </h2>
        <JobList refreshKey={refresh} />
      </section>
    </div>
  );
}
