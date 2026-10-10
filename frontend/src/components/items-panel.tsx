"use client";

import { useEffect, useState } from "react";
import { api, type Item } from "@/lib/api";

export function ItemsPanel() {
  const [items, setItems] = useState<Item[]>([]);
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [version, setVersion] = useState(0);
  const load = () => setVersion((v) => v + 1);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        await api.health();
        const page = await api.listItems();
        if (active) {
          setHealth("ok");
          setItems(page.items);
        }
      } catch {
        if (active) setHealth("down");
      }
    })();
    return () => {
      active = false;
    };
  }, [version]);

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createItem({ name, description: description || undefined });
      setName("");
      setDescription("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(id: number) {
    await api.deleteItem(id);
    load();
  }

  return (
    <div className="grid gap-5 md:grid-cols-[1fr_1.4fr]">
      <section className="card flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-heading-sm font-semibold">New item</h2>
          <span
            className={`badge ${health === "ok" ? "bg-ink-soft text-surface-alt" : "border border-hairline text-mid-gray"}`}
          >
            API {health}
          </span>
        </div>
        <form onSubmit={onCreate} className="flex flex-col gap-2">
          <input
            className="input"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <input
            className="input"
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          {error && <p className="text-caption text-ember">{error}</p>}
          <div className="flex gap-2 pt-2">
            <button type="submit" className="btn-primary" disabled={busy || !name}>
              Create
            </button>
            <button type="button" className="btn-secondary" onClick={load}>
              Refresh
            </button>
          </div>
        </form>
      </section>

      <section className="card flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-heading-sm font-semibold">Items</h2>
          <span className="text-caption uppercase text-mid-gray">{items.length} total</span>
        </div>
        {items.length === 0 ? (
          <p className="text-mid-gray">No items yet.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-hairline">
            {items.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="font-medium">{item.name}</p>
                  {item.description && (
                    <p className="truncate text-mid-gray">{item.description}</p>
                  )}
                </div>
                <button
                  className="btn-outline text-ember"
                  onClick={() => onDelete(item.id)}
                  aria-label={`Delete ${item.name}`}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
