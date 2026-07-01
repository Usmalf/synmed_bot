import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { fetchHealthTips } from "../api/admin.js";
import RevealOnScroll from "../components/RevealOnScroll.jsx";
import "../styles/landing.css";

const featureCards = [
  {
    title: "Talk to a doctor from home",
    body: "Start a consultation without sitting in a waiting room or wondering what to do next.",
  },
  {
    title: "Get care you can follow",
    body: "Receive prescriptions, test requests, and follow-up guidance after your consultation.",
  },
  {
    title: "Find help when you need it",
    body: "Our support team can help with login, payments, documents, and getting back to your care.",
  },
];

const doctorHighlights = [
  {
    name: "Dr. Usman Mohammad Alfa",
    specialty: "General Physician",
    note: "Available for everyday symptoms, follow-up care, and clear medical guidance.",
    rating: "4.9",
  },
  {
    name: "Dr. Akubo Sylvanus",
    specialty: "General Physician",
    note: "Helpful support for family health concerns, including children and women's health.",
    rating: "4.9",
  },
  {
    name: "Dr. Amir Jibril",
    specialty: "General Practice",
    note: "Primary care support for urgent symptoms, prescriptions, and referrals when needed.",
    rating: "4.9",
  },
];

const workflow = [
  {
    step: "01",
    title: "Sign in or register",
    body: "Create your patient account or return with your existing details.",
  },
  {
    step: "02",
    title: "Start your consultation",
    body: "Tell us your symptoms and wait for a doctor to join your chat.",
  },
  {
    step: "03",
    title: "Receive your care plan",
    body: "Get medical advice, prescriptions, investigations, or follow-up instructions.",
  },
];

const proofStats = [
  { value: "24 hrs", label: "to continue after payment" },
  { value: "Online", label: "doctor consultations" },
  { value: "Easy", label: "access to prescriptions and tests" },
];

const trustPoints = [
  "Speak with verified medical doctors",
  "Return to your care without starting all over",
  "Find prescriptions and test requests after consultation",
  "Keep your health history easy to reach",
];

const testimonials = [
  {
    quote: "It was easy to know what to do next after I signed in.",
    name: "Patient Experience",
  },
  {
    quote: "I got to see my doctor quickly and smoothly, all from home.",
    name: "Patient Experience 2",
  },
  {
    quote: "The follow-up and documents were easy to find after my consultation.",
    name: "Patient Experience 3",
  },
];

const fallbackHealthTips = [
  {
    eyebrow: "Health Tip",
    title: "Drink water regularly, not only when you feel thirsty.",
    body: "Mild dehydration can worsen headaches, tiredness, and poor concentration, especially during hot days.",
  },
  {
    eyebrow: "Health Tip",
    title: "Check blood pressure early if headaches keep returning.",
    body: "Routine checks help catch silent problems like hypertension before they become emergencies.",
  },
  {
    eyebrow: "Health Tip",
    title: "Do not self-medicate repeatedly for the same symptoms.",
    body: "When symptoms keep coming back, a proper consultation is usually safer than trying another drug on your own.",
  },
  {
    eyebrow: "SynMed Update",
    title: "Keep your medical profile updated for faster care.",
    body: "Accurate allergies, phone number, and previous diagnoses help doctors make quicker and safer decisions.",
  },
];

function SocialIcon({ type }) {
  if (type === "telegram") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M21.7 4.3 18.4 20c-.2 1-1 1.2-1.8.7l-5-3.7-2.4 2.3c-.3.3-.5.5-1 .5l.4-5.1 9.3-8.4c.4-.4-.1-.6-.6-.3L5.8 13.2.9 11.7c-1.1-.3-1.1-1.1.2-1.6L20.3 2.7c.9-.3 1.7.2 1.4 1.6Z" />
      </svg>
    );
  }

  if (type === "whatsapp") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M12 2a9.8 9.8 0 0 0-8.5 14.7L2.3 22l5.4-1.2A9.9 9.9 0 1 0 12 2Zm0 2a7.9 7.9 0 0 1 6.8 11.9 7.8 7.8 0 0 1-9.8 3l-.4-.2-3.1.7.7-3-.2-.4A7.8 7.8 0 0 1 12 4Zm-3.1 4.1c-.2 0-.6.1-.9.5-.3.4-1.1 1.1-1.1 2.6s1.1 3 1.2 3.2c.1.2 2.1 3.4 5.2 4.6 2.6 1 3.1.8 3.7.7.6-.1 1.8-.8 2-1.5.3-.7.3-1.3.2-1.5-.1-.1-.3-.2-.7-.4l-2.1-1c-.3-.1-.5-.2-.7.2l-.9 1.1c-.2.2-.4.3-.7.1-.4-.2-1.4-.5-2.6-1.6-1-.9-1.6-2-1.8-2.4-.2-.3 0-.5.2-.7l.5-.6c.2-.2.2-.3.3-.5.1-.2 0-.4 0-.6L9.8 8.7c-.2-.5-.5-.6-.9-.6Z" />
      </svg>
    );
  }

  if (type === "instagram") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M7.5 2h9A5.5 5.5 0 0 1 22 7.5v9a5.5 5.5 0 0 1-5.5 5.5h-9A5.5 5.5 0 0 1 2 16.5v-9A5.5 5.5 0 0 1 7.5 2Zm0 2A3.5 3.5 0 0 0 4 7.5v9A3.5 3.5 0 0 0 7.5 20h9a3.5 3.5 0 0 0 3.5-3.5v-9A3.5 3.5 0 0 0 16.5 4h-9Zm4.5 3.4A4.6 4.6 0 1 1 12 16.6 4.6 4.6 0 0 1 12 7.4Zm0 2A2.6 2.6 0 1 0 12 14.6 2.6 2.6 0 0 0 12 9.4Zm5-2.6a1.1 1.1 0 1 1-1.1 1.1A1.1 1.1 0 0 1 17 6.8Z" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M14 8.2V6.9c0-.6.4-.9 1-.9h1.8V2.8c-.9-.1-1.8-.2-2.7-.2-2.7 0-4.5 1.6-4.5 4.6v1H6.8v3.6h2.8V22H14V11.8h2.9l.5-3.6H14Z" />
    </svg>
  );
}

export default function LandingPage() {
  const location = useLocation();
  const [activeTipIndex, setActiveTipIndex] = useState(0);
  const [healthTips, setHealthTips] = useState(fallbackHealthTips);

  useEffect(() => {
    if (!healthTips.length) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      setActiveTipIndex((current) => (current + 1) % healthTips.length);
    }, 7000);

    return () => window.clearInterval(intervalId);
  }, [healthTips.length]);

  useEffect(() => {
    let ignore = false;

    async function loadTips() {
      try {
        const result = await fetchHealthTips();
        if (!ignore && result.tips?.length) {
          setHealthTips(result.tips);
          setActiveTipIndex(0);
        }
      } catch {}
    }

    loadTips();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (location.hash !== "#contact") {
      return;
    }

    window.requestAnimationFrame(() => {
      document.getElementById("contact")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }, [location.hash]);

  const activeTip = healthTips[activeTipIndex];

  function showPreviousTip() {
    setActiveTipIndex((current) => (current - 1 + healthTips.length) % healthTips.length);
  }

  function showNextTip() {
    setActiveTipIndex((current) => (current + 1) % healthTips.length);
  }

  return (
    <div className="landing-page">
      <section className="landing-hero">
        <div className="landing-hero__copy">
          <p className="landing-hero__eyebrow">SynMed Telehealth</p>
          <h1 className="landing-hero__title">
            Quality healthcare service.
            <br />
            Anywhere, Anytime.
          </h1>

          <div className="landing-hero__actions">
            <Link className="button button--primary" to="/signin">
              Patient Login
            </Link>
            <Link className="button landing-hero__cta-alt" to="/patient/register">
              Get Started
            </Link>
          </div>
        </div>

        <div className="landing-hero__aside">
          <div className="landing-hero__image-wrap" aria-hidden="true">
            <img className="landing-hero__image" src="/nigerian-doctor-tele.png" alt="" />
          </div>

          <div className="landing-proof-grid">
            {proofStats.map((item) => (
              <article key={item.label} className="landing-proof-card">
                <strong>{item.value}</strong>
                <span>{item.label}</span>
              </article>
            ))}
          </div>
        </div>
      </section>

      <RevealOnScroll delay={20}>
        <section className="landing-section landing-section--feature-grid">
        <div className="landing-section__heading">
          <h2>Care that is simple to start.</h2>
        </div>

        {featureCards.map((item) => (
          <article key={item.title} className="landing-feature-card">
            <h3>{item.title}</h3>
            <p>{item.body}</p>
          </article>
        ))}
        </section>
      </RevealOnScroll>

      <RevealOnScroll delay={80}>
        <section className="landing-tip-panel">
        <button
          className="landing-tip-panel__arrow landing-tip-panel__arrow--prev"
          type="button"
          aria-label="Previous tip"
          onClick={showPreviousTip}
        >
          &#8249;
        </button>
        <div key={activeTip.title} className="landing-tip-panel__copy landing-tip-panel__copy--animated">
          <p className="landing-kicker">{activeTip.eyebrow}</p>
          <h2>{activeTip.title}</h2>
          <p>{activeTip.body}</p>
        </div>
        <div className="landing-tip-panel__dots" aria-label="Health tips rotation">
          {healthTips.map((tip, index) => (
            <button
              key={tip.title}
              className={
                index === activeTipIndex
                  ? "landing-tip-panel__dot landing-tip-panel__dot--active"
                  : "landing-tip-panel__dot"
              }
              type="button"
              aria-label={`Show tip ${index + 1}`}
              onClick={() => setActiveTipIndex(index)}
            />
          ))}
        </div>
        <button
          className="landing-tip-panel__arrow landing-tip-panel__arrow--next"
          type="button"
          aria-label="Next tip"
          onClick={showNextTip}
        >
          &#8250;
        </button>
        </section>
      </RevealOnScroll>

      <RevealOnScroll delay={120}>
        <section className="landing-section landing-section--split">
        <div className="landing-section__heading">
          <h2>How to get care on SynMed.</h2>
        </div>

        <div className="landing-flow">
          {workflow.map((item) => (
            <article key={item.step} className="landing-flow-card">
              <span className="landing-flow-card__step">{item.step}</span>
              <div>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </div>
            </article>
          ))}
        </div>
        </section>
      </RevealOnScroll>

      <RevealOnScroll delay={140}>
        <section className="landing-section">
        <div className="landing-section__heading">
          <h2>Meet our doctors.</h2>
        </div>

        <div className="landing-doctor-grid">
          {doctorHighlights.map((doctor) => (
            <article key={doctor.name} className="landing-doctor-card">
              <span className="landing-doctor-card__badge">{doctor.specialty}</span>
              <h3>{doctor.name}</h3>
              <p>{doctor.note}</p>
              <div className="landing-doctor-card__footer">
                <span>{doctor.rating} / 5 rating</span>
              </div>
            </article>
          ))}
        </div>
        </section>
      </RevealOnScroll>

      <RevealOnScroll delay={160}>
        <section className="landing-strip">
        <div className="landing-strip__copy">
          <h2>Why patients choose SynMed.</h2>
        </div>
        <div className="landing-strip__list">
          {trustPoints.map((item) => (
            <article key={item} className="landing-strip__item">
              <span className="landing-strip__dot" />
              <p>{item}</p>
            </article>
          ))}
        </div>
        </section>
      </RevealOnScroll>

      <RevealOnScroll delay={170}>
        <section className="landing-visual-band">
        <div className="landing-visual-band__media">
          <div className="landing-visual-band__image-wrap">
            <img
              className="landing-visual-band__image"
              src="/section-image.png"
              alt="Doctor consulting with a patient remotely"
            />
          </div>
        </div>
        <div className="landing-visual-band__copy">
          <h2>Telehealth works better when it still feels human.</h2>
          <div className="landing-visual-band__points">
            <article>
              <strong>Fast response</strong>
              <span>Start your request and get connected without unnecessary delays.</span>
            </article>
            <article>
              <strong>Easy follow-up</strong>
              <span>Your history, prescriptions, and test requests stay easy to find.</span>
            </article>
          </div>
        </div>
        </section>
      </RevealOnScroll>

      <RevealOnScroll delay={180}>
        <section className="landing-section">
        <div className="landing-section__heading">
          <h2>What patients say about the experience.</h2>
        </div>

        <div className="landing-testimonials">
          {testimonials.map((item) => (
            <article key={item.name} className="landing-testimonial-card">
              <p>&ldquo;{item.quote}&rdquo;</p>
              <span>{item.name}</span>
            </article>
          ))}
        </div>
        </section>
      </RevealOnScroll>

      <RevealOnScroll delay={240}>
        <footer className="landing-footer">
        <div className="landing-footer__brand">
          <h3>Your health in sync.</h3>
          <img className="landing-footer__logo" src="/logo-removebg-preview.png" alt="SynMed Telehealth" />
          <div className="landing-footer__socials" aria-label="SynMed social media">
            <a href="https://t.me/SynmedTelehealth" target="_blank" rel="noreferrer" aria-label="SynMed Telegram page" title="Telegram page">
              <SocialIcon type="telegram" />
            </a>
            <a href="https://wa.me/2348107840312" target="_blank" rel="noreferrer" aria-label="SynMed WhatsApp" title="WhatsApp">
              <SocialIcon type="whatsapp" />
            </a>
            <a href="https://www.instagram.com/synmedtelehealth?igsh=b2g0a2RpZDZuMmRl" target="_blank" rel="noreferrer" aria-label="SynMed Instagram" title="Instagram">
              <SocialIcon type="instagram" />
            </a>
            <a href="https://www.facebook.com/share/18qQSJpBXQ/" target="_blank" rel="noreferrer" aria-label="SynMed Facebook" title="Facebook">
              <SocialIcon type="facebook" />
            </a>
          </div>
        </div>

        <div className="landing-footer__column">
          <span className="landing-footer__heading">Quick Links</span>
          <div className="landing-footer__links">
            <Link to="/">Home</Link>
            <Link to="/patient">Patients</Link>
            <Link to="/doctor">Doctors</Link>
            <Link to="/signin">Sign In</Link>
            <Link to="/terms">Terms of Use</Link>
            <Link to="/privacy">Privacy Policy</Link>
          </div>
        </div>

        <div className="landing-footer__column" id="contact">
          <span className="landing-footer__heading">Contact Us</span>
          <div className="landing-footer__contact">
            <a className="landing-footer__contact-link" href="mailto:support@synmed.ng">
              <span className="landing-footer__contact-icon" aria-hidden="true">✉</span>
              <span>synmedtelehealth@gmail.com</span>
            </a>
            <a className="landing-footer__contact-link" href="tel:+2348000000000">
              <span className="landing-footer__contact-icon" aria-hidden="true">◔</span>
              <span>+234 810 784 0312</span>
            </a>
            <a className="landing-footer__contact-link" href="https://t.me/SynmedTelehealth" target="_blank" rel="noreferrer">
              <span className="landing-footer__contact-icon" aria-hidden="true"><SocialIcon type="telegram" /></span>
              <span>Telegram page</span>
            </a>
            <a className="landing-footer__contact-link" href="https://t.me/Synmed2_bot" target="_blank" rel="noreferrer">
              <span className="landing-footer__contact-icon" aria-hidden="true"><SocialIcon type="telegram" /></span>
              <span>Telegram bot</span>
            </a>
            <span>Available for patient support and care.</span>
          </div>
        </div>
        <div className="landing-footer__copyright">
          &copy; 2026 SynMed Telehealth. All rights reserved.
        </div>
        </footer>
      </RevealOnScroll>
    </div>
  );
}
