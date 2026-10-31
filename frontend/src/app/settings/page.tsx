'use client';

import { useEffect, useState } from 'react';
import {
  Check,
  Cpu,
  Save,
} from 'lucide-react';
import { GithubIcon } from '@/components/GithubIcon';
import { Header } from '@/components/Header';
import { getSettings, updateSettings, SettingsData } from '@/lib/api';

export default function SettingsPage() {
  const [data, setData] = useState<SettingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  // Form states
  const [aiProvider, setAiProvider] = useState('qwen');
  const [confidenceThreshold, setConfidenceThreshold] = useState('0.75');

  const loadSettings = async () => {
    try {
      setLoading(true);
      const res = await getSettings();
      setData(res);
      setAiProvider(res.settings.ai_provider || 'qwen');
      setConfidenceThreshold(res.settings.confidence_threshold || '0.75');
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      await updateSettings({
        ai_provider: aiProvider,
        confidence_threshold: confidenceThreshold,
      });
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 3000);
    } catch (err) {
      alert('Failed to save settings: ' + err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Header
        title="Settings &amp; Engine Configuration"
        subtitle="Manage the verification engine and confidence threshold"
      />

      <main className="p-6 space-y-6 flex-1 overflow-y-auto max-w-4xl mx-auto w-full">
        <form onSubmit={handleSave} className="space-y-6">
          {/* Analysis Engine Selection */}
          <div className="bg-card border border-border p-6 rounded-lg space-y-5">
            <div className="flex items-center space-x-3 border-b border-border pb-4">
              <Cpu className="w-4 h-4 text-white" />
              <div>
                <h3 className="text-xs font-semibold text-white uppercase tracking-wider font-mono">
                  Verification Engine
                </h3>
                <p className="text-xs text-zinc-400">
                  Select the evaluator for comparing code revisions against documentation prose.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                {
                  id: 'qwen',
                  name: 'Rules + Qwen 2.5 Coder 3B',
                  desc: 'Rules decide exact matches. A small open-weight model on this machine decides if a paraphrased sentence is about the changed setting. Uses about 2 GB of memory.',
                },
                {
                  id: 'heuristic',
                  name: 'Rules only',
                  desc: 'Exact matching with no model. Instant, but only certain when a sentence names the changed setting.',
                },
              ].map((prov) => (
                <label
                  key={prov.id}
                  className={`p-4 rounded-lg cursor-pointer transition border block space-y-2 ${
                    aiProvider === prov.id
                      ? 'border-white bg-zinc-900 text-white'
                      : 'border-border bg-black hover:border-zinc-700 text-zinc-400'
                  }`}
                >
                  <input
                    type="radio"
                    name="ai_provider"
                    value={prov.id}
                    checked={aiProvider === prov.id}
                    onChange={(e) => setAiProvider(e.target.value)}
                    className="sr-only"
                  />
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-xs text-white font-mono">{prov.name}</span>
                    {aiProvider === prov.id && (
                      <span className="h-2 w-2 rounded-full bg-white"></span>
                    )}
                  </div>
                  <p className="text-[11px] text-zinc-400 leading-relaxed">{prov.desc}</p>
                </label>
              ))}
            </div>

            <div className="flex items-center justify-between p-3.5 rounded bg-black border border-border text-xs font-mono">
              <span className="text-zinc-300">Ollama ({data?.system.model ?? 'model'})</span>
              {data?.system.model_ready ? (
                <span className="text-emerald-400 flex items-center space-x-1.5">
                  <Check className="w-3.5 h-3.5" />
                  <span>Ready</span>
                </span>
              ) : (
                <span className="text-amber-400">
                  {data?.system.ollama_running ? `Run: ollama pull ${data.system.model}` : 'Not running: start Ollama'}
                </span>
              )}
            </div>

            <div className="pt-2 space-y-2">
              <div className="flex justify-between items-center text-xs font-mono">
                <span className="text-zinc-400">Confidence Threshold:</span>
                <span className="text-white font-bold">{Math.round(Number(confidenceThreshold) * 100)}%</span>
              </div>
              <input
                type="range"
                min="0.5"
                max="0.95"
                step="0.05"
                value={confidenceThreshold}
                onChange={(e) => setConfidenceThreshold(e.target.value)}
                className="w-full accent-white bg-zinc-800 h-1.5 rounded-lg appearance-none cursor-pointer"
              />
              <span className="text-[11px] text-zinc-500 font-mono block">
                Evaluations with confidence below this threshold are flagged as POSSIBLE DRIFT rather than CONFIRMED DRIFT.
              </span>
            </div>
          </div>

          {/* GitHub Integration Status */}
          <div className="bg-card border border-border p-6 rounded-lg space-y-5">
            <div className="flex items-center space-x-3 border-b border-border pb-4">
              <GithubIcon className="w-4 h-4 text-white" />
              <div>
                <h3 className="text-xs font-semibold text-white uppercase tracking-wider font-mono">
                  GitHub Integration &amp; Webhook Security
                </h3>
                <p className="text-xs text-zinc-400">
                  Signature validation for webhooks sent by GitHub.
                </p>
              </div>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="flex items-center justify-between p-3.5 rounded bg-black border border-border">
                <span className="text-zinc-300">Webhook HMAC-SHA256 Signature</span>
                <span className="text-zinc-300">
                  {data?.system.github_webhook_secret_configured ? 'Enabled (HMAC-SHA256)' : 'Development Mode'}
                </span>
              </div>

            </div>
          </div>

          {/* Save Action Bar */}
          <div className="flex items-center justify-between pt-2">
            <div>
              {savedSuccess && (
                <span className="text-xs text-emerald-400 font-mono flex items-center space-x-1.5">
                  <Check className="w-4 h-4" />
                  <span>Configuration saved and persisted.</span>
                </span>
              )}
            </div>

            <button
              type="submit"
              disabled={saving}
              className="flex items-center space-x-2 text-xs font-semibold bg-white hover:bg-zinc-200 text-black px-5 py-2.5 rounded transition disabled:opacity-50 font-mono shadow-sm"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{saving ? 'Saving...' : 'Save Configuration'}</span>
            </button>
          </div>
        </form>
      </main>
    </>
  );
}