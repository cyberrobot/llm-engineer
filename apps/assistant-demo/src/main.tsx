import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { AssistantWidgetDemo } from './AssistantWidgetDemo'
import './demo.css'

const root = document.getElementById('root')

if (!root) throw new Error('Assistant demo root element was not found.')

createRoot(root).render(
  <StrictMode>
    <AssistantWidgetDemo />
  </StrictMode>,
)
