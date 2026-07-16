import Image from "next/image";
import Link from "next/link";
import { ArrowRight, BarChart3, CalendarClock, Coins, PenLine, RadioTower, Search, ShieldCheck, Sparkles } from "lucide-react";

const features = [
  {
    title: "Account-scoped generation",
    body: "Every draft, credit event, and publish queue belongs to the active account."
  },
  {
    title: "Live AI drafting",
    body: "Streaming generation renders tokens as they arrive, with clear credit visibility."
  },
  {
    title: "Credit marketplace",
    body: "Owners can buy credits, sell surplus balances, and review account transactions."
  },
  {
    title: "Social scheduling",
    body: "Draft content can move from studio to calendar to LinkedIn without losing context."
  }
];

const tiers = [
  { name: "Starter", price: "$29", detail: "Solo operators testing an AI-assisted publishing workflow." },
  { name: "Pro", price: "$149", detail: "Owners managing credits, drafts, and a regular publishing cadence." },
  { name: "Scale", price: "$399", detail: "Teams with role controls, marketplace operations, and admin oversight." }
];

export default function HomePage() {
  return (
    <main className="public-shell">
      <section className="hero landing-frame">
        <Image
          className="landing-bg"
          src="/creditflow-hero.png"
          alt="CreditFlow dashboard preview"
          fill
          sizes="(max-width: 900px) 100vw, 1180px"
          priority
        />
        <div className="landing-shade" />
        <nav className="marketing-nav" aria-label="Public">
          <Link className="brand" href="/">
            <span className="brand-mark">
              <BarChart3 size={18} aria-hidden="true" />
            </span>
            CreditFlow
          </Link>
          <div className="nav-links">
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
            <Link href="/login">Log in</Link>
          </div>
          <div className="public-actions">
            <Link className="button ghost" href="/login">
              Log in
            </Link>
            <Link className="button primary" href="/signup">
              Sign up
            </Link>
          </div>
        </nav>

        <div className="hero-main">
          <div className="hero-copy">
            <div className="hero-tags" aria-label="CreditFlow modes">
              <span>Studio</span>
              <span>Credits</span>
              <span>Scheduler</span>
            </div>
            <h1>
              Build Your Content Engine, <em>One Flow</em> at a Time
            </h1>
            <p>Multi-tenant AI generation, credit control, and social publishing in one account-scoped workspace.</p>
            <div className="hero-actions">
              <Link className="button primary" href="/signup">
                Start building
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
              <Link className="button secondary" href="/login">
                Open workspace
              </Link>
            </div>
          </div>

          <div className="hero-product-stack" aria-label="CreditFlow workflow preview">
            <div className="workflow-card workflow-card-primary">
              <div className="workflow-card-header">
                <span className="workflow-icon"><Sparkles size={18} aria-hidden="true" /></span>
                <span>AI Content Studio</span>
              </div>
              <strong>Generate a LinkedIn-ready post from research, drafts, or a fresh prompt.</strong>
              <div className="workflow-progress" aria-hidden="true"><span /></div>
            </div>
            <div className="workflow-grid">
              <div className="workflow-card compact">
                <span className="workflow-icon"><Search size={16} aria-hidden="true" /></span>
                <strong>Research</strong>
                <p>Topic or URL scraper</p>
              </div>
              <div className="workflow-card compact">
                <span className="workflow-icon"><PenLine size={16} aria-hidden="true" /></span>
                <strong>Draft</strong>
                <p>Versioned content</p>
              </div>
              <div className="workflow-card compact">
                <span className="workflow-icon"><CalendarClock size={16} aria-hidden="true" /></span>
                <strong>Schedule</strong>
                <p>Calendar handoff</p>
              </div>
              <div className="workflow-card compact">
                <span className="workflow-icon"><RadioTower size={16} aria-hidden="true" /></span>
                <strong>Publish</strong>
                <p>LinkedIn pipeline</p>
              </div>
            </div>
            <div className="workflow-metric-row">
              <div><span>Credits tracked</span><strong>12.4k</strong></div>
              <div><span>Drafts saved</span><strong>286</strong></div>
              <div><span>Posts queued</span><strong>42</strong></div>
            </div>
          </div>
        </div>

        <div className="hero-search-panel" aria-label="Find your CreditFlow workspace">
          <div className="search-panel-header">
            <span>Find your workflow</span>
            <span className="search-availability">
              <ShieldCheck size={14} aria-hidden="true" />
              2,481 active workspaces
            </span>
          </div>
          <div className="search-panel-grid">
            <div className="search-field">
              <Coins size={17} aria-hidden="true" />
              <div>
                <span>Credit scope</span>
                <strong>Any account type</strong>
              </div>
            </div>
            <div className="search-field">
              <RadioTower size={17} aria-hidden="true" />
              <div>
                <span>AI pipeline</span>
                <strong>Live generation</strong>
              </div>
            </div>
            <div className="search-field">
              <CalendarClock size={17} aria-hidden="true" />
              <div>
                <span>Publishing</span>
                <strong>LinkedIn schedule</strong>
              </div>
            </div>
            <Link className="button search-button" href="/login">
              <Search size={16} aria-hidden="true" />
              Open Demo
            </Link>
          </div>
        </div>
      </section>

      <section className="section" id="features">
        <div className="section-heading">
          <h2 className="section-title">Built for account-level control</h2>
          <p>CreditFlow keeps billing, credits, content, sessions, and audit events scoped to the selected account.</p>
        </div>
        <div className="feature-grid">
          {features.map((feature, index) => {
            const icons = [Coins, RadioTower, BarChart3, CalendarClock];
            const Icon = icons[index];
            return (
              <article className="feature-card" key={feature.title}>
                <Icon size={22} color="var(--color-primary)" aria-hidden="true" />
                <h3>{feature.title}</h3>
                <p>{feature.body}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="section" id="pricing">
        <div className="section-heading">
          <h2 className="section-title">Pricing that follows usage</h2>
          <p>Owners can add credits directly, upgrade plans, or buy from other accounts in the marketplace.</p>
        </div>
        <div className="pricing-grid">
          {tiers.map((tier) => (
            <article className="price-card" key={tier.name}>
              <h3>{tier.name}</h3>
              <div className="price">
                {tier.price}
                <span>/mo</span>
              </div>
              <p>{tier.detail}</p>
              <Link className="button secondary" href="/signup">
                Choose {tier.name}
                <ArrowRight size={15} aria-hidden="true" />
              </Link>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
