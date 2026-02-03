import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="card" style={{ textAlign: 'left' }}>
      <h3 style={{ marginTop: 0 }}>Not Found</h3>
      <div>
        Go to <Link to="/market">/market</Link>
      </div>
    </div>
  )
}
