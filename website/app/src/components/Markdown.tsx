import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cx } from './ui'

/** Safe markdown (no raw HTML) for diary entries, notes and world models. */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cx('prose-md', className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  )
}
