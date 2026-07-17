import { useEffect, useRef } from 'react'

export default function GeometricBg() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    let animId
    // Grid spacings from DESIGN.md: 78px 68px 98px 240px 48px
    const GRID_A = 78
    const GRID_B = 240

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    // Particles drifting along the grid
    const makeParticle = () => ({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      vx: (Math.random() - 0.5) * 0.25,
      vy: (Math.random() - 0.5) * 0.25,
      r: Math.random() * 1.2 + 0.3,
      a: Math.random() * 0.25 + 0.05,
    })
    const particles = Array.from({ length: 28 }, makeParticle)

    // Scan pulses — vertical lines that travel across the canvas
    const pulses = [
      { x: Math.random() * window.innerWidth, speed: 0.15 + Math.random() * 0.1 },
      { x: Math.random() * window.innerWidth, speed: 0.18 + Math.random() * 0.08 },
    ]

    let frame = 0

    const draw = () => {
      const W = canvas.width, H = canvas.height
      ctx.clearRect(0, 0, W, H)

      // Fine grid — very dim
      ctx.strokeStyle = 'rgba(255,255,255,0.035)'
      ctx.lineWidth = 1
      for (let x = 0; x < W; x += GRID_A) {
        ctx.beginPath(); ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H); ctx.stroke()
      }
      for (let y = 0; y < H; y += GRID_A) {
        ctx.beginPath(); ctx.moveTo(0, y + 0.5); ctx.lineTo(W, y + 0.5); ctx.stroke()
      }

      // Coarser structural grid — slightly brighter
      ctx.strokeStyle = 'rgba(255,255,255,0.06)'
      ctx.lineWidth = 1
      for (let x = 0; x < W; x += GRID_B) {
        ctx.beginPath(); ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H); ctx.stroke()
      }
      for (let y = 0; y < H; y += GRID_B) {
        ctx.beginPath(); ctx.moveTo(0, y + 0.5); ctx.lineTo(W, y + 0.5); ctx.stroke()
      }

      // Intersection nodes at coarse grid
      for (let x = 0; x <= W; x += GRID_B) {
        for (let y = 0; y <= H; y += GRID_B) {
          ctx.beginPath()
          ctx.arc(x, y, 2, 0, Math.PI * 2)
          ctx.fillStyle = 'rgba(255,255,255,0.12)'
          ctx.fill()
        }
      }

      // Drifting particles
      particles.forEach(p => {
        p.x += p.vx; p.y += p.vy
        if (p.x < 0) p.x = W
        if (p.x > W) p.x = 0
        if (p.y < 0) p.y = H
        if (p.y > H) p.y = 0
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(255,255,255,${p.a})`
        ctx.fill()
      })

      // Vertical scan pulses
      pulses.forEach(pulse => {
        pulse.x += pulse.speed
        if (pulse.x > W) pulse.x = -4

        const grad = ctx.createLinearGradient(pulse.x - 40, 0, pulse.x + 40, 0)
        grad.addColorStop(0, 'rgba(255,255,255,0)')
        grad.addColorStop(0.5, 'rgba(255,255,255,0.045)')
        grad.addColorStop(1, 'rgba(255,255,255,0)')
        ctx.fillStyle = grad
        ctx.fillRect(pulse.x - 40, 0, 80, H)
      })

      frame++
      animId = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 0,
      }}
    />
  )
}
