import { Component, type ReactNode } from 'react';

/** Workflow failures must never unmount the Studio navigation or saved board. */
export class WorkflowBoundary extends Component<{
  children: ReactNode;
  fallback: (retry: () => void) => ReactNode;
}, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed
      ? this.props.fallback(() => this.setState({ failed: false }))
      : this.props.children;
  }
}
