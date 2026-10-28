// The frame and the sky window (blueprint §4.3.3). Screens fill in with T35–T45.

export function App() {
  return (
    <>
      <a class="skip" href="#memories">
        Skip to the list of memories
      </a>
      <div class="frame">
        <aside class="column" aria-label="Moira">
          <h1 class="wordmark">Moira</h1>
          <p class="scope">Everything you save becomes a star.</p>
          <div id="memories" tabIndex={-1} />
        </aside>
        <main class="window">
          <canvas
            class="sky-canvas"
            role="img"
            aria-label="Your memories as a night sky. Each star is one memory, coloured by its age from blue-white for new to amber for old, and grouped into constellations by topic."
          />
        </main>
      </div>
    </>
  );
}
