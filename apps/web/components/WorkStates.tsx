export function WorkError({ message }: { message: string }) {
  return <div className="state state-error" role="alert">{message}</div>;
}

export function WorkLoading() {
  return <div className="state" role="status">Loading...</div>;
}

export function WorkEmpty({ message }: { message: string }) {
  return <div className="state">{message}</div>;
}

