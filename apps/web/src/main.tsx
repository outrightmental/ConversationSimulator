// SPDX-License-Identifier: Apache-2.0
import React from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import App from './App'
import './index.css'

// Data router (createBrowserRouter) is required for useBlocker to work (e.g. the
// dirty-state navigation guard in CreatorWorkbench). BrowserRouter does not
// provide the blocking infrastructure. The catch-all route delegates all path
// matching to the <Routes> tree inside App.
const router = createBrowserRouter(
  [{ path: '*', element: <App /> }],
  { future: { v7_relativeSplatPath: true } },
)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
)
