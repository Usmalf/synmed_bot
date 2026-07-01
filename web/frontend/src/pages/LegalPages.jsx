import { Link } from "react-router-dom";
import "../styles/legal.css";

const termsSections = [
  {
    title: "Use of SynMed Services",
    body: [
      "SynMed Telehealth Ltd provides telehealth consultation, appointment, prescription support, investigation request, medical report, payment, customer support, and related digital healthcare services.",
      "By using the platform, users agree to provide true, accurate, current, and complete information, use the services only for lawful purposes, and follow platform instructions."
    ],
  },
  {
    title: "Medical and Emergency Notice",
    body: "SynMed supports remote healthcare delivery, but online consultation is not a substitute for emergency care. Users with severe symptoms or urgent conditions should seek immediate in-person emergency medical attention.",
  },
  {
    title: "Payment and Financial Responsibility",
    body: "Fees for consultations, subscriptions, prescription support, diagnostic coordination, medical reports, or related services are subject to the pricing communicated at the relevant time.",
    bullets: [
      "Users are responsible for supplying accurate, valid, and authorised payment information.",
      "SynMed is not liable for failed payments, declined transactions, delayed settlements, bank restrictions, network downtime, or payment gateway errors outside its control.",
      "Fees paid for services already rendered may be non-refundable except where required by law, duplicate billing is proven, a system error is confirmed, or cancellation is attributable to SynMed.",
      "SynMed may suspend or restrict services where payment obligations remain outstanding or fraud is reasonably suspected."
    ],
  },
  {
    title: "User Account Responsibilities",
    bullets: [
      "Keep passwords, devices, login credentials, and authentication codes confidential.",
      "Secure personal devices used to access SynMed services.",
      "Promptly notify SynMed of suspected unauthorised access or account compromise.",
      "Do not misuse, hack, reverse engineer, interfere with, impersonate another person, or use the platform for fraudulent activity.",
      "Comply with applicable laws, healthcare instructions, and platform guidance."
    ],
  },
  {
    title: "Service Availability and Third-Party Services",
    body: "SynMed works to maintain reasonable technical, organisational, and administrative safeguards, but no digital platform, network, server, database, communications system, or third-party integration can be guaranteed to be completely secure, uninterrupted, or free from vulnerabilities.",
    bullets: [
      "SynMed may rely on third-party providers including payment processors, cloud vendors, telecommunications providers, laboratories, pharmacies, and other service partners.",
      "SynMed is not liable for losses caused solely by independent acts, omissions, outages, delays, or security failures of third parties beyond its reasonable control."
    ],
  },
  {
    title: "Limitation of Liability",
    body: "To the fullest extent permitted by law, SynMed Telehealth Ltd, its directors, officers, employees, contractors, agents, affiliates, and authorised service providers shall not be liable for indirect, incidental, punitive, special, exemplary, or consequential loss connected with use of, inability to use, or reliance on the services.",
    bullets: [
      "This includes loss of profits, business interruption, reputational damage, data loss or delay, network or electricity failure, service interruption by third parties, compromised user credentials, or reliance on incomplete third-party information.",
      "Where liability is established, SynMed's aggregate liability shall, to the maximum extent permitted by law, be limited to the amount paid by the affected user for the specific service giving rise to the claim within the twelve months before the event complained of.",
      "Nothing excludes liability for fraud, fraudulent misrepresentation, wilful misconduct, gross negligence, death or personal injury where non-excludable, or any liability which cannot lawfully be excluded."
    ],
  },
  {
    title: "Indemnity",
    body: "Users agree to indemnify and hold harmless SynMed Telehealth Ltd, its directors, officers, employees, agents, contractors, affiliates, licensors, and service providers against claims, liabilities, damages, losses, penalties, costs, and reasonable legal fees arising from misuse of the platform, breach of these terms or policies, false information, unlawful acts, unauthorised use of identity, payment method or data, or negligent, reckless, or wilful conduct.",
  },
  {
    title: "Force Majeure",
    body: "SynMed shall not be liable for delay, interruption, or failure in performance arising from events beyond its reasonable control, including acts of God, fire, flood, epidemic, pandemic, war, riot, labour disputes, widespread cyber incidents, regulatory restrictions, telecommunications failure, or power outage.",
  },
  {
    title: "Dispute Resolution and Governing Law",
    body: [
      "Disputes, complaints, billing issues, platform matters, data processing issues, or legal disagreements should first be referred for good-faith discussions and internal complaint review.",
      "If unresolved, parties may proceed to mediation and then arbitration in accordance with the Arbitration and Mediation Act or any statutory modification. The seat and venue of arbitration shall be Abuja, Federal Capital Territory, Nigeria, unless otherwise agreed, and the language shall be English.",
      "These terms and related disputes are governed by the laws of the Federal Republic of Nigeria. Courts in Nigeria retain supervisory and enforcement jurisdiction where applicable."
    ],
  },
];

const privacySections = [
  {
    title: "Introduction and Scope",
    body: [
      "SynMed Telehealth Ltd is committed to protecting the privacy, confidentiality, and security of personal data entrusted to it by patients, users, staff, vendors, and other stakeholders.",
      "This Privacy Policy explains how SynMed collects, uses, discloses, stores, transfers, retains, and protects personal data while providing telehealth consultation and related healthcare support services.",
      "This policy is intended to comply with applicable laws including the Nigeria Data Protection Act 2023, the Nigeria Data Protection Regulation, and relevant subsidiary regulations."
    ],
  },
  {
    title: "Definitions",
    bullets: [
      "Personal data means information relating to an identified or identifiable individual.",
      "Sensitive personal data includes health information, medical history, biometric data, and other sensitive categories recognised by law.",
      "Processing means collection, storage, use, disclosure, transfer, deletion, or any handling of personal data.",
      "Data subject means the person whose data is processed."
    ],
  },
  {
    title: "Information We Collect",
    body: "SynMed may collect data needed for care delivery, account management, payment, support, compliance, and platform safety.",
    bullets: [
      "Personal identification information such as full name, date of birth, gender, nationality, and profile image where provided.",
      "Contact details such as address, email, telephone number, and emergency contact details where applicable.",
      "Account and registration information including account ID, login credentials, encrypted passwords, preferences, and communication settings.",
      "Health and medical information including medical history, symptoms, consultation notes, diagnosis records, prescriptions, laboratory results, treatment plans, and health insurance information where applicable.",
      "Financial and payment information including payment references, billing details, transaction history, invoices, and receipts.",
      "Technical, device, usage, platform, location, employment, support, feedback, complaint, and uploaded document information."
    ],
  },
  {
    title: "How We Collect Data",
    bullets: [
      "Website registration forms and telemedicine consultation portals.",
      "Mobile applications and digital platforms where applicable.",
      "Customer support channels and email communications.",
      "Payment platforms, cookies, analytics tools, and approved third-party integrations."
    ],
  },
  {
    title: "Purpose and Legal Basis of Processing",
    body: "SynMed processes personal data for lawful purposes connected with service delivery and compliance.",
    bullets: [
      "Providing medical consultations, booking appointments, facilitating prescriptions and referrals, coordinating pharmacies and laboratories, verifying identity, processing payments, managing accounts, responding to inquiries, improving service quality, preventing fraud, and meeting legal or regulatory obligations.",
      "SynMed may rely on consent, performance of a contract, compliance with legal obligations, protection of vital interests, or legitimate business interests where lawful."
    ],
  },
  {
    title: "Health Data and Confidentiality",
    body: "As a telehealth provider, SynMed processes health-related information. Such data is handled with strict confidentiality controls, used for medical service delivery, processed with explicit consent where required, and accessed by authorised personnel only.",
  },
  {
    title: "Data Sharing",
    body: "SynMed does not sell personal data. Data may be shared only where necessary and lawful.",
    bullets: [
      "Licensed healthcare practitioners, pharmacies, diagnostic laboratories, payment processors, cloud hosting providers, legal or regulatory authorities, and approved operational service providers may receive relevant information where required for the service.",
      "Third parties are expected to be subject to confidentiality, security, and data protection obligations."
    ],
  },
  {
    title: "Security Measures",
    body: "SynMed implements appropriate technical, administrative, organisational, and physical safeguards to protect personal data against accidental or unlawful destruction, loss, alteration, unauthorised disclosure, misuse, or access.",
    bullets: [
      "Measures may include encryption, secure authentication, password protection, firewalls, protected cloud infrastructure, software updates, backups, recovery systems, role-based access, confidentiality obligations, staff training, vendor due diligence, physical record controls, incident response, and periodic security review."
    ],
  },
  {
    title: "Data Retention and Disposal",
    body: "SynMed retains personal data only for as long as reasonably necessary for the purpose collected, continuity of care, contractual obligations, dispute resolution, enforcement of legal rights, and statutory or regulatory requirements.",
    bullets: [
      "Patient and medical records may be retained for continuity of care, clinical reference, medico-legal purposes, and healthcare or legal obligations.",
      "Account, registration, financial, transaction, employment, marketing, and communication records are retained according to operational need and applicable law.",
      "When data is no longer required, SynMed takes reasonable steps to delete, anonymise, archive, or securely dispose of it."
    ],
  },
  {
    title: "Data Subject Rights",
    body: "Subject to applicable law, individuals may request access to data, correction of inaccuracies, deletion where lawful, restriction of processing, withdrawal of consent, and complaint review.",
  },
  {
    title: "Children and Minors",
    body: "Where services are provided to or data is collected from minors, SynMed processes such data only in accordance with applicable law and appropriate safeguards. Where required, consent of a parent, legal guardian, or authorised representative will be obtained. Parents or lawful guardians may exercise relevant privacy rights on behalf of a child subject to law.",
  },
  {
    title: "Cookies and Tracking Technologies",
    body: "SynMed may use cookies, pixels, web beacons, SDKs, analytics tools, and similar technologies to enhance functionality, secure login and sessions, remember preferences, analyse traffic, monitor performance, detect fraud or abuse, improve content, and support lawful communications where consent is required.",
  },
  {
    title: "Third-Party Links and International Transfers",
    body: [
      "SynMed platforms may contain third-party links or integrations. Those platforms are independent unless expressly stated, and users should review their privacy policies and terms before submitting personal data.",
      "Where operationally necessary, personal data may be transferred, stored, accessed, or processed outside Nigeria through cloud infrastructure, technology vendors, or authorised service providers, subject to lawful basis and appropriate safeguards."
    ],
  },
  {
    title: "Policy Updates, Breach Management, and Contact",
    body: [
      "SynMed may update this policy to reflect changes in law, regulation, business operations, technology, security practices, or services. Revised versions become effective when published unless otherwise stated.",
      "Suspected breaches will be investigated promptly, and affected persons or regulators will be notified where required by law.",
      "Privacy inquiries may be directed to SynMed Telehealth Ltd through its official communication channels."
    ],
  },
];

function LegalPage({ eyebrow, title, intro, sections, sourceNote }) {
  return (
    <main className="legal-page">
      <section className="legal-hero">
        <span>{eyebrow}</span>
        <h1>{title}</h1>
        <p>{intro}</p>
        {sourceNote ? <p className="legal-hero__source">{sourceNote}</p> : null}
        <Link className="button button--secondary" to="/">
          Back to home
        </Link>
      </section>

      <section className="legal-content">
        {sections.map((section) => (
          <article key={section.title} className="legal-card">
            <h2>{section.title}</h2>
            {Array.isArray(section.body) ? (
              section.body.map((paragraph) => <p key={paragraph}>{paragraph}</p>)
            ) : section.body ? (
              <p>{section.body}</p>
            ) : null}
            {section.bullets?.length ? (
              <ul>
                {section.bullets.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
          </article>
        ))}
      </section>
    </main>
  );
}

export function TermsPage() {
  return (
    <LegalPage
      eyebrow="SynMed Telehealth"
      title="Terms and Conditions of Use"
      intro="These terms explain the conditions for using SynMed Telehealth, including user responsibilities, payment obligations, liability limits, third-party services, and dispute resolution."
      sourceNote="Updated from the SynMed Telehealth Ltd Data Protection Compliance Document Pack sealed on 28 April 2026."
      sections={termsSections}
    />
  );
}

export function PrivacyPage() {
  return (
    <LegalPage
      eyebrow="SynMed Telehealth"
      title="Privacy Policy"
      intro="This policy explains how SynMed Telehealth Ltd collects, uses, shares, retains, transfers, and protects personal data while providing telehealth and related healthcare support services."
      sourceNote="Updated from the SynMed Telehealth Ltd Data Protection Compliance Document Pack sealed on 28 April 2026."
      sections={privacySections}
    />
  );
}
