// SPDX-License-Identifier: Apache-2.0
import type { UseSetupFlowReturn } from './useSetupFlow'
import { WelcomeStep } from './steps/WelcomeStep'
import { LoadingStep } from './steps/LoadingStep'
import { LoadErrorStep } from './steps/LoadErrorStep'
import { PreflightStep } from './steps/PreflightStep'
import { ChooseStep } from './steps/ChooseStep'
import { ConfirmInstallStep } from './steps/ConfirmInstallStep'
import { InstallingStep } from './steps/InstallingStep'
import { BenchmarkStep } from './steps/BenchmarkStep'
import { OllamaSelectStep } from './steps/OllamaSelectStep'
import { GgufPathStep } from './steps/GgufPathStep'
import { DemoConfirmStep } from './steps/DemoConfirmStep'

interface SetupFlowViewProps {
  flow: UseSetupFlowReturn
  mode: 'wizard' | 'manager'
}

export function SetupFlowView({ flow, mode }: SetupFlowViewProps) {
  switch (flow.step) {
    case 'welcome':
      return <WelcomeStep flow={flow} />
    case 'loading':
      return <LoadingStep flow={flow} mode={mode} />
    case 'load-error':
      return <LoadErrorStep flow={flow} mode={mode} />
    case 'preflight':
      return <PreflightStep flow={flow} />
    case 'choose':
      return <ChooseStep flow={flow} mode={mode} />
    case 'confirm-install':
      return <ConfirmInstallStep flow={flow} mode={mode} />
    case 'installing':
      return <InstallingStep flow={flow} mode={mode} />
    case 'benchmark':
      return <BenchmarkStep flow={flow} mode={mode} onComplete={flow.handleFinishBenchmark} />
    case 'ollama-select':
      return <OllamaSelectStep flow={flow} mode={mode} />
    case 'gguf-path':
      return <GgufPathStep flow={flow} mode={mode} />
    case 'demo-warning':
      return <DemoConfirmStep flow={flow} mode={mode} />
    default:
      return null
  }
}
