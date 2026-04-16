export interface EvidenceInterpretation {
  chart_type?: string;
  main_message?: string;
  entities?: string[];
  metrics?: string[];
  trend?: string;
  evidence_text?: string;
  confidence?: number;
}

export interface EvidenceHighlight {
  page?: number;
  bbox?: number[];
  line_start?: number;
  line_end?: number;
  page_width?: number;
  page_height?: number;
}

export interface EvidenceSource {
  id?: string;
  source: string;
  page: number | string;
  line_start?: number;
  line_end?: number;
  bbox?: number[];
  page_width?: number;
  page_height?: number;
  highlight_boxes?: EvidenceHighlight[];
  title?: string;
  content?: string;
  summary?: string;
  excerpt?: string;
  score?: number;
  file_id?: string;
  asset_id?: string;
  asset_type?: string;
  caption?: string;
  ref_label?: string;
  thumbnail_url?: string;
  interpretation?: EvidenceInterpretation;
  is_primary?: boolean;
  evidence_kind?: string;
}

const UUID_PREFIX_PATTERNS = [
  /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_(.+)$/i,
  /^(?:[0-9a-f]{24,32})_(.+)$/i,
];

export function cleanEvidenceTitle(source?: string): string {
  const raw = String(source || '').split('/').pop() || '';
  if (!raw) return '来源';

  let cleaned = raw;
  let changed = true;
  while (changed) {
    changed = false;
    for (const pattern of UUID_PREFIX_PATTERNS) {
      const match = cleaned.match(pattern);
      if (match?.[1]) {
        cleaned = match[1];
        changed = true;
        break;
      }
    }
  }

  cleaned = cleaned.replace(/\.(pdf|txt|md|docx?)$/i, '');
  cleaned = cleaned.replace(/_+/g, ' ').replace(/\s+/g, ' ').trim();
  return cleaned || '来源';
}
