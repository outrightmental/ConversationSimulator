// SPDX-License-Identifier: Apache-2.0
import { useSetupFlow, SetupFlowView } from '../setup'

export default function ModelManager() {
  const flow = useSetupFlow('loading')
  return <SetupFlowView flow={flow} mode="manager" />
}
