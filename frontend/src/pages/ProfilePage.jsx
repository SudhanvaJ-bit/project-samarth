export default function ProfilePage() {
  return (
    <>
      <header className="page-header">
        <div><h2>Profile</h2><p>Manage your account details and credentials.</p></div>
      </header>
      <div className="profile-layout">
        <div className="card">
          <div className="profile-header-main">
            <img src="https://ui-avatars.com/api/?name=Dr.+Smith&background=f8f8f9&color=050508&size=120" alt="Dr. Smith" className="profile-huge-avatar" />
            <h3>Dr. Sarah Smith</h3>
            <p className="role-badge">Lead Special Educator</p>
            <p className="profile-email">sarah.smith@samarth.edu</p>
          </div>
          <div className="profile-stats">
            <div className="p-stat"><h4>142</h4><span>IEPs Generated</span></div>
            <div className="p-stat"><h4>34</h4><span>Active Students</span></div>
          </div>
        </div>
        <div className="card">
          <div className="card-header"><h3>Personal Information</h3></div>
          <div className="modern-form">
            <div className="form-row">
              <div className="form-group"><label>First Name</label><input type="text" defaultValue="Sarah" /></div>
              <div className="form-group"><label>Last Name</label><input type="text" defaultValue="Smith" /></div>
            </div>
            <div className="form-group"><label>Email Address</label><input type="email" defaultValue="sarah.smith@samarth.edu" /></div>
            <div className="form-group"><label>School / District</label><input type="text" defaultValue="Westside Unified School District" /></div>
            <div className="form-actions"><button className="btn btn-primary" style={{ flex: '0 0 auto' }}>Update Profile</button></div>
          </div>
          <div className="card-header" style={{ borderTop: '1px solid rgba(255,255,255,0.04)', marginTop: 20 }}><h3>Security</h3></div>
          <div className="modern-form">
            <div className="form-group"><label>Current Password</label><input type="password" placeholder="••••••••" /></div>
            <div className="form-row">
              <div className="form-group"><label>New Password</label><input type="password" placeholder="••••••••" /></div>
              <div className="form-group"><label>Confirm Password</label><input type="password" placeholder="••••••••" /></div>
            </div>
            <div className="form-actions"><button className="btn btn-secondary" style={{ flex: '0 0 auto' }}>Change Password</button></div>
          </div>
        </div>
      </div>
    </>
  )
}