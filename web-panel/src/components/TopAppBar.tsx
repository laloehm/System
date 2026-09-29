import React from 'react';

export default function TopAppBar() {
  return (
    <header className="w-full top-0 sticky z-50 bg-surface-container-lowest border-b border-outline-variant flex justify-between items-center px-margin-mobile md:px-margin-desktop h-16">
      <div className="flex items-center gap-md">
        <span className="material-symbols-outlined text-primary-container" style={{ fontVariationSettings: "'FILL' 1" }}>terminal</span>
        <span className="font-label-caps text-label-caps tracking-widest text-primary-container ml-2">COMMAND CENTER</span>
      </div>
      <div className="flex items-center gap-md">
        <div className="text-right hidden md:block">
          <p className="font-label-caps text-[10px] text-on-surface-variant">SESSION ACTIVE</p>
          <p className="font-body-sm text-on-surface">Admin User</p>
        </div>
        <div className="w-10 h-10 rounded-full bg-secondary-container flex items-center justify-center overflow-hidden border border-outline-variant">
          <img
            alt="Admin headshot"
            className="w-full h-full object-cover"
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuDN36esPDgI3MG73DA6U4txBm2YmofLcYC4wgiPSb4RFxbIlVfMGuJAOGaDDQVPBn8wiwb3y9NA--1C5Qe4Bi3ZHrJWqUWP5lLZo2kWxHxh9NuA-o6ys-XQOlG18_KRqsEAJ2qPdINi9KoSFZ8MMncX9GyGTJtVNDy4H9vMDryO3UvQm5W_69fScYyNmPS5qKWJzSWdLEacgkyf9qQrguptb5B8hkPhLvYJ-wrUcfTyUqnWDpqPJzkC8Q"
          />
        </div>
        <a
          href="/auth/logout"
          title="Cerrar sesión"
          className="p-2 rounded-full hover:bg-surface-container-high text-on-surface-variant"
        >
          <span className="material-symbols-outlined block">logout</span>
        </a>
      </div>
    </header>
  );
}
