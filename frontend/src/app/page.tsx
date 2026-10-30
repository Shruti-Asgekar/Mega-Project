import Link from 'next/link';

const steps = [
  { n: 1, icon: '📄', title: 'Upload your documents', desc: 'Securely submit Aadhaar, PAN, salary slip, and bank statement.' },
  { n: 2, icon: '🔍', title: 'We read and check everything', desc: 'Our system reads, extracts, and cross-verifies every detail automatically.' },
  { n: 3, icon: '📊', title: 'Risk and fraud review', desc: 'A loan officer reviews the AI-generated report and makes a recommendation.' },
  { n: 4, icon: '✅', title: 'Final decision by a manager', desc: 'A senior manager gives the final approval. You get notified instantly.' },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Hero */}
      <header className="bg-white dark:bg-gray-900 border-b">
        <nav className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <span className="text-xl font-bold text-accent-700 dark:text-accent-400">KYC Loan Platform</span>
          <Link href="/login" className="btn-primary text-sm py-2 px-4">
            Sign In
          </Link>
        </nav>
      </header>

      <main className="flex-1">
        {/* Hero Section */}
        <section className="max-w-4xl mx-auto px-6 py-20 text-center">
          <div className="inline-flex items-center gap-2 bg-accent-50 dark:bg-accent-900/20 text-accent-700 dark:text-accent-300 text-sm font-medium px-4 py-2 rounded-full mb-6">
            <span>🔒</span> Secure · Private · Free
          </div>
          <h1 className="text-4xl md:text-5xl font-bold mb-6 leading-tight">
            Smart loan processing that reads, checks, and protects your documents — automatically.
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-400 mb-10 max-w-2xl mx-auto">
            Upload your KYC documents once. Our system verifies them, flags problems, and prepares a complete report for your loan officer — in minutes, not days.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/login" className="btn-primary text-lg">
              Apply Now
            </Link>
            <Link href="/login?demo=true" className="btn-secondary text-lg">
              View Demo
            </Link>
          </div>
        </section>

        {/* How it Works */}
        <section className="bg-gray-50 dark:bg-gray-950 py-16">
          <div className="max-w-5xl mx-auto px-6">
            <h2 className="text-3xl font-bold text-center mb-12">How it works</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {steps.map(step => (
                <div key={step.n} className="card text-center hover:shadow-md transition-shadow">
                  <div className="text-4xl mb-4">{step.icon}</div>
                  <div className="text-xs font-bold text-accent-600 dark:text-accent-400 uppercase tracking-wide mb-2">Step {step.n}</div>
                  <h3 className="font-semibold text-lg mb-3">{step.title}</h3>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">{step.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Trust Signals */}
        <section className="max-w-4xl mx-auto px-6 py-16 text-center">
          <h2 className="text-2xl font-bold mb-8">Built for trust</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="card">
              <div className="text-3xl mb-3">🛡️</div>
              <h3 className="font-semibold mb-2">Privacy first</h3>
              <p className="text-gray-500 dark:text-gray-400 text-sm">Your Aadhaar and PAN are always masked. Staff only see partial numbers.</p>
            </div>
            <div className="card">
              <div className="text-3xl mb-3">🤝</div>
              <h3 className="font-semibold mb-2">Humans decide</h3>
              <p className="text-gray-500 dark:text-gray-400 text-sm">AI flags issues as signals. A human officer and a manager make the final call.</p>
            </div>
            <div className="card">
              <div className="text-3xl mb-3">🔗</div>
              <h3 className="font-semibold mb-2">Tamper-proof records</h3>
              <p className="text-gray-500 dark:text-gray-400 text-sm">Every document is sealed with a cryptographic fingerprint. Any change is instantly detected.</p>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t py-8 text-center text-gray-500 text-sm">
        <p>KYC Loan Platform · All data is synthetic · For demonstration purposes only</p>
      </footer>
    </div>
  );
}
