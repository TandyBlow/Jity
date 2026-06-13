"use client";

import { ArrowLeft, CalendarDays, GitCommit, Search, Tags } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import type { DevLogEntry } from "@/lib/dev-log";

export function DevLogView({ entries }: { entries: DevLogEntry[] }) {
  const [query, setQuery] = useState("");
  const [area, setArea] = useState("all");

  const areas = useMemo(() => {
    return Array.from(new Set(entries.flatMap((entry) => entry.areas))).sort();
  }, [entries]);

  const filteredEntries = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return entries.filter((entry) => {
      const matchesArea = area === "all" || entry.areas.includes(area);
      const searchableText = [
        entry.title,
        entry.summary,
        entry.author,
        ...entry.areas,
        ...entry.changes,
        ...entry.relatedFiles,
        ...(entry.nextSteps ?? []),
      ]
        .join(" ")
        .toLowerCase();

      return matchesArea && (!normalizedQuery || searchableText.includes(normalizedQuery));
    });
  }, [area, entries, query]);

  return (
    <main className="dev-log-shell">
      <header className="dev-log-header">
        <div>
          <Link className="back-link" href="/">
            <ArrowLeft size={16} />
            回到控制台
          </Link>
          <h1>开发日志</h1>
          <p>内部记录每次有意义的代码改动、影响范围和后续待办，方便团队成员快速接上当前进度。</p>
        </div>
        <div className="dev-log-count">
          <strong>{entries.length}</strong>
          <span>entries</span>
        </div>
      </header>

      <section className="dev-log-tools" aria-label="开发日志筛选">
        <label className="search-field" htmlFor="dev-log-search">
          <Search size={16} />
          <input
            id="dev-log-search"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索标题、文件、改动内容"
            type="search"
            value={query}
          />
        </label>

        <label className="area-field" htmlFor="dev-log-area">
          <Tags size={16} />
          <select id="dev-log-area" onChange={(event) => setArea(event.target.value)} value={area}>
            <option value="all">全部范围</option>
            {areas.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="dev-log-list" aria-live="polite">
        {filteredEntries.length ? (
          filteredEntries.map((entry) => <DevLogEntryCard entry={entry} key={entry.id} />)
        ) : (
          <div className="empty-log">没有匹配的开发日志。</div>
        )}
      </section>
    </main>
  );
}

function DevLogEntryCard({ entry }: { entry: DevLogEntry }) {
  return (
    <article className="dev-log-entry">
      <div className="entry-topline">
        <div className="entry-date">
          <CalendarDays size={15} />
          <time dateTime={entry.date}>{entry.date}</time>
        </div>
        <div className="entry-author">
          <GitCommit size={15} />
          {entry.author}
        </div>
      </div>

      <h2>{entry.title}</h2>
      <p className="entry-summary">{entry.summary}</p>

      <div className="tag-row">
        {entry.areas.map((item) => (
          <span className="area-tag" key={item}>
            {item}
          </span>
        ))}
      </div>

      <LogSection items={entry.changes} title="本次改动" />
      <FileList files={entry.relatedFiles} />
      {entry.nextSteps?.length ? <LogSection items={entry.nextSteps} title="后续事项" /> : null}
    </article>
  );
}

function LogSection({ items, title }: { items: string[]; title: string }) {
  return (
    <section className="entry-section">
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function FileList({ files }: { files: string[] }) {
  return (
    <section className="entry-section">
      <h3>相关文件</h3>
      <div className="file-list">
        {files.map((file) => (
          <code key={file}>{file}</code>
        ))}
      </div>
    </section>
  );
}
