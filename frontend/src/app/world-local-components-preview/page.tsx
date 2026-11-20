import type { Metadata } from 'next';

import { ComponentsPreview } from './ComponentsPreview';

/** Internal component-check route. It is deliberately noindex and never the
 * game entry: /world-local remains the only playable browser-local page. */
export const metadata: Metadata = {
  title: '组件预览 · Jity',
  robots: { index: false, follow: false },
};

export default function Page() {
  return <ComponentsPreview />;
}
