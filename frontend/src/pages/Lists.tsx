import { useEffect, useState, type FormEvent } from "react";
import { api, type Contact, type List } from "../lib/api";
import {
  Card,
  Empty,
  ErrorBanner,
  PageHeader,
  Spinner,
  SuccessBanner,
  errMessage,
} from "../components/ui";

export default function Lists() {
  const [lists, setLists] = useState<List[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // create
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // add contacts
  const [targetList, setTargetList] = useState<string>("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [assigning, setAssigning] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);
  const [assignDone, setAssignDone] = useState<string | null>(null);

  async function load() {
    try {
      const [l, c] = await Promise.all([
        api.get<List[]>("/api/lists"),
        api.get<Contact[]>("/api/contacts"),
      ]);
      setLists(l);
      setContacts(c);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreating(true);
    try {
      const created = await api.post<List>("/api/lists", {
        name,
        description: description || undefined,
      });
      setLists((prev) => [...prev, created]);
      setName("");
      setDescription("");
    } catch (err) {
      setCreateError(errMessage(err));
    } finally {
      setCreating(false);
    }
  }

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function onAssign(e: FormEvent) {
    e.preventDefault();
    setAssignError(null);
    setAssignDone(null);
    if (!targetList) {
      setAssignError("Pick a list first.");
      return;
    }
    if (selected.size === 0) {
      setAssignError("Select at least one contact.");
      return;
    }
    setAssigning(true);
    try {
      const res = await api.post<{ added: number }>(
        `/api/lists/${targetList}/contacts`,
        { contact_ids: Array.from(selected) },
      );
      setAssignDone(`Added ${res.added} contact(s) to the list.`);
      setSelected(new Set());
    } catch (err) {
      setAssignError(errMessage(err));
    } finally {
      setAssigning(false);
    }
  }

  return (
    <div>
      <PageHeader title="Lists" subtitle="Static groups of contacts." />
      <ErrorBanner message={error} />

      <div className="grid-2">
        <Card title="Create a list">
          <ErrorBanner message={createError} />
          <form onSubmit={onCreate} className="form">
            <label className="field">
              <span>Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Newsletter subscribers"
                required
              />
            </label>
            <label className="field">
              <span>Description (optional)</span>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="People who opted in via the footer form"
              />
            </label>
            <button className="btn btn-primary" disabled={creating}>
              {creating ? "Creating…" : "Create list"}
            </button>
          </form>
        </Card>

        <Card title="Your lists">
          {loading ? (
            <Spinner />
          ) : lists.length === 0 ? (
            <Empty message="No lists yet." />
          ) : (
            <ul className="simple-list">
              {lists.map((l) => (
                <li key={l.id}>
                  <div className="simple-list-main">
                    <strong>{l.name}</strong>
                    {l.description ? (
                      <span className="muted">{l.description}</span>
                    ) : null}
                  </div>
                  <span className="muted mono">#{l.id}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Add contacts to a list">
        <ErrorBanner message={assignError} />
        <SuccessBanner message={assignDone} />
        {loading ? (
          <Spinner />
        ) : (
          <form onSubmit={onAssign} className="form">
            <label className="field">
              <span>Target list</span>
              <select
                value={targetList}
                onChange={(e) => setTargetList(e.target.value)}
              >
                <option value="">— Pick a list —</option>
                {lists.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>

            {contacts.length === 0 ? (
              <Empty message="No contacts available to add." />
            ) : (
              <div className="table-wrap select-table">
                <table className="table">
                  <thead>
                    <tr>
                      <th className="checkcol"></th>
                      <th>Email</th>
                      <th>Name</th>
                    </tr>
                  </thead>
                  <tbody>
                    {contacts.map((c) => (
                      <tr
                        key={c.id}
                        className={selected.has(c.id) ? "row-selected" : ""}
                      >
                        <td className="checkcol">
                          <input
                            type="checkbox"
                            checked={selected.has(c.id)}
                            onChange={() => toggle(c.id)}
                          />
                        </td>
                        <td className="mono">{c.email}</td>
                        <td>{c.name || <span className="muted">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <button className="btn btn-primary" disabled={assigning}>
              {assigning
                ? "Adding…"
                : `Add ${selected.size || ""} selected to list`}
            </button>
          </form>
        )}
      </Card>
    </div>
  );
}
