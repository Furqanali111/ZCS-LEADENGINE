"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, deleteSavedSearch, listSavedSearches, type SavedSearch } from "@/lib/api";

export function summarize(s: SavedSearch) {
  return [s.specialty, s.city ? `${s.city}, ${s.state}` : s.state, `${s.target_count} leads`].join(" · ");
}

export function SavedSearches({ refreshKey, onUse }: { refreshKey: number; onUse: (s: SavedSearch) => void }) {
  const [items, setItems] = useState<SavedSearch[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;
    listSavedSearches()
      .then((l) => !stale && (setItems(l), setError(null)))
      .catch((e: Error) => !stale && setError(e.message));
    return () => {
      stale = true;
    };
  }, [refreshKey]);

  async function remove(s: SavedSearch) {
    if (!window.confirm(`Delete the saved search "${s.name}"?`)) return;
    try {
      await deleteSavedSearch(s.id);
      setItems((cur) => cur?.filter((x) => x.id !== s.id) ?? null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete the saved search.");
    }
  }

  return (
    <section aria-labelledby="saved-searches" className="border-b pb-5">
      <h3 id="saved-searches" className="mb-2 text-sm font-medium">
        Saved searches
      </h3>
      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
      {items?.length === 0 && <p className="text-sm text-muted-foreground">None yet. Fill in the form and use Save this search.</p>}
      {items && items.length > 0 && (
        <ul className="max-h-48 divide-y overflow-y-auto">
          {items.map((s) => (
            <li key={s.id} className="flex items-center gap-2 py-1.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{s.name}</p>
                <p className="truncate text-sm text-muted-foreground">{summarize(s)}</p>
              </div>
              <Button type="button" variant="outline" size="sm" aria-label={`Use saved search ${s.name}`} onClick={() => onUse(s)}>
                Use
              </Button>
              <Button type="button" variant="ghost" size="sm" aria-label={`Delete saved search ${s.name}`} onClick={() => remove(s)}>
                Delete
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
