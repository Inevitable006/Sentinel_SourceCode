import React from 'react';
import type { ModelsInfo } from '../../lib/backend';

export interface ModelStatusProps {
  info: ModelsInfo | null;
  activeProfile: string;
}

/**
 * Presentational component rendering honest model and GPU engine status.
 *
 * Distinguishes:
 * - Selected profile vs actually loaded model
 * - Downloaded vs loadable vs automatic policy
 * - GPU engine availability vs running inference
 * - Honest unmeasured VRAM (never reports measured zero for missing VRAM)
 */
export const ModelStatus: React.FC<ModelStatusProps> = ({ info, activeProfile }) => {
  if (!info) {
    return <p className="settings-desc">Loading model information…</p>;
  }

  const selected = info.profiles.find(p => p.id === activeProfile);
  const isAutoPolicy = selected?.id === 'auto' || selected?.downloaded === null;
  const isDownloaded = selected?.downloaded === true;
  const isNotDownloaded = selected?.downloaded === false;

  // GPU Engine VRAM reading: never show 0.0 GB if VRAM is missing/unmeasured
  const gpu = info.gpu_engine;
  let gpuText = 'not reported';
  if (gpu) {
    if (gpu.available) {
      const vramStr = typeof gpu.vram_mb === 'number' && gpu.vram_mb > 0
        ? `${(gpu.vram_mb / 1024).toFixed(1)} GB VRAM`
        : 'VRAM: unmeasured';
      gpuText = gpu.running ? `running (${vramStr})` : `ready (${vramStr})`;
    } else {
      gpuText = `unavailable (${gpu.reason ?? 'hardware or driver not detected'})`;
    }
  }

  const loaded = info.loaded;
  const isDifferentFromActive = Boolean(
    loaded && loaded.profile_id && activeProfile && loaded.profile_id !== activeProfile
  );

  return (
    <div className="model-status-container" style={{ marginTop: '0.5rem' }}>
      <p className="settings-desc" style={{ margin: '0.25rem 0' }}>
        <strong>Selected profile:</strong> {selected?.name ?? activeProfile}
        {' — '}
        {isAutoPolicy
          ? 'Automatic selection policy (picks best downloaded model)'
          : isDownloaded
          ? 'Downloaded (ready to load)'
          : isNotDownloaded
          ? 'Not downloaded (GGUF file missing in models folder)'
          : 'Status unverified'}
      </p>

      <p className="settings-desc" style={{ margin: '0.25rem 0' }}>
        <strong>Loaded in memory:</strong>{' '}
        {loaded && (loaded.name || loaded.profile_id)
          ? `${loaded.name ?? loaded.profile_id} on ${loaded.engine ? loaded.engine.toUpperCase() : 'engine'}`
          : 'No model loaded right now.'}
        {isDifferentFromActive && (
          <span style={{ display: 'block', color: 'var(--accent-secondary, #fbbf24)', fontSize: '0.85rem', marginTop: '0.15rem' }}>
            Note: Selected profile differs from currently loaded model. Re-load model in Console to apply.
          </span>
        )}
      </p>

      <p className="settings-desc" style={{ margin: '0.25rem 0' }}>
        <strong>GPU engine:</strong> {gpuText}
      </p>

      {(loaded?.notes?.length ?? 0) > 0 && (
        <p className="settings-desc" style={{ margin: '0.25rem 0' }}>
          <strong>Selection / fallback notes:</strong> {loaded!.notes.join(' · ')}
        </p>
      )}

      {!loaded && info.last_load_error && (
        <p className="settings-desc" role="alert" style={{ color: 'var(--color-danger, #f87171)', margin: '0.25rem 0' }}>
          <strong>Last load error:</strong> {info.last_load_error}
        </p>
      )}

      <p className="settings-desc" style={{ fontSize: '0.8rem', opacity: 0.85, marginTop: '0.5rem' }}>
        Model weights, context cache, and runtime all consume memory. Sentinel's runtime load and fit checks remain authoritative.
      </p>
    </div>
  );
};

export default ModelStatus;

