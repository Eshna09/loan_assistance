/**
 * staticData.js
 * Loan-only fallback values used when the backend is offline.
 */

export const STATIC_KB_INFO = {
  documents: [
    {
      filename: 'loans.txt',
      preview: 'A loan is money borrowed from a lender and repaid over time, usually with interest. The borrower receives funds upfront and agrees',
      chunk_count: 5,
      full_text: 'A loan is money borrowed from a lender and repaid over time, usually with interest. The borrower receives funds upfront and agrees to repay the principal plus borrowing costs according to a schedule. Common loan types include personal loans, home loans or mortgages, auto loans, education loans, and business loans. The main parts of a loan are the principal, interest rate, term, repayment frequency, fees, and collateral if the loan is secured. The principal is the amount borrowed. Interest is the cost charged by the lender. The term is how long the borrower has to repay. Fees may include processing fees, late fees, prepayment charges, or documentation charges. Loans can be secured or unsecured. A secured loan is backed by collateral such as a house, car, deposit, or other asset. If the borrower does not repay, the lender may have a legal claim on the collateral. An unsecured loan does not use collateral, so lenders rely more heavily on the borrower\'s income, credit history, and repayment capacity. This assistant provides general educational information about loans. It does not provide personalized lending, legal, tax, or financial advice.',
    },
    {
      filename: 'loan_types.txt',
      preview: 'Personal loans are usually unsecured loans used for flexible personal expenses. They often have faster approval but may carry higher interest',
      chunk_count: 4,
      full_text: 'Personal loans are usually unsecured loans used for flexible personal expenses. They often have faster approval but may carry higher interest rates than secured loans. Home loans or mortgages are secured by property and are usually long-term loans. Because the property acts as collateral, rates may be lower than unsecured loans, but default can put the property at risk. Auto loans are used to buy vehicles and are commonly secured by the vehicle. Education loans help pay for tuition and related study costs. Business loans provide capital for business needs such as working capital, equipment, inventory, or expansion. The suitable loan type depends on the purpose, repayment capacity, cost, term, collateral requirement, and risk. Borrowers should compare offers using total cost, not only interest rate or EMI.',
    },
    {
      filename: 'loan_interest.txt',
      preview: 'Loan interest is the cost of borrowing money. It is usually expressed as an annual percentage rate. A fixed interest rate stays',
      chunk_count: 4,
      full_text: 'Loan interest is the cost of borrowing money. It is usually expressed as an annual percentage rate. A fixed interest rate stays the same during the loan period, while a variable or floating interest rate can change based on a benchmark or lender policy. Simple interest is calculated on the original principal. Compound interest can add unpaid interest to the balance, causing interest to be charged on interest. Many installment loans use an amortization schedule, where each payment includes both interest and principal repayment. In the early part of an amortized loan, a larger share of each payment often goes toward interest. Over time, as the outstanding balance falls, more of each payment goes toward reducing principal. Comparing only the monthly payment can be misleading; borrowers should also compare total interest paid and total repayment amount.',
    },
    {
      filename: 'loan_repayment.txt',
      preview: 'Loan repayment is the process of paying back borrowed money according to the agreed schedule. Many loans are repaid through EMIs or fixed',
      chunk_count: 4,
      full_text: 'Loan repayment is the process of paying back borrowed money according to the agreed schedule. Many loans are repaid through EMIs or fixed installments. An EMI usually includes interest for the period plus part of the principal balance. Missing a repayment can lead to late fees, penalty interest, credit score impact, collection activity, or legal consequences depending on the loan agreement. If repayment becomes difficult, borrowers should contact the lender early to ask about restructuring, deferment, revised payment dates, or hardship options. Prepayment means paying extra toward the loan before it is due. Prepayment can reduce total interest because the outstanding principal falls sooner. Some lenders charge prepayment fees, so borrowers should check whether the savings are greater than the charges.',
    },
    {
      filename: 'loan_eligibility.txt',
      preview: 'Loan eligibility is the lender\'s assessment of whether a borrower can responsibly repay. Lenders commonly review income, employment stability, existing debt',
      chunk_count: 4,
      full_text: 'Loan eligibility is the lender\'s assessment of whether a borrower can responsibly repay. Lenders commonly review income, employment stability, existing debt, credit history, repayment track record, age, residence, requested loan amount, loan purpose, and available collateral. Credit score is one factor in many loan decisions. A higher score can indicate lower repayment risk, but it is not the only factor. Lenders may also calculate debt-to-income ratio, which compares monthly debt payments with monthly income. A lower debt-to-income ratio generally leaves more room for a new loan payment. Documents requested for loan applications often include identity proof, address proof, income proof, bank statements, tax documents, employment details, property papers for secured loans, and vehicle or education documents for specific loan types.',
    },
    {
      filename: 'loan_risks.txt',
      preview: 'Loans create repayment obligations, so borrowers should understand the risks before accepting funds. Borrowing more than needed can increase interest costs and monthly',
      chunk_count: 4,
      full_text: 'Loans create repayment obligations, so borrowers should understand the risks before accepting funds. Borrowing more than needed can increase interest costs and monthly pressure. A low EMI may still be expensive if the loan term is very long. Important costs to review include the interest rate, processing fee, insurance cost, late payment fee, penalty interest, foreclosure or prepayment fee, documentation charge, and taxes. Borrowers should read the sanction letter and repayment schedule carefully before signing. Secured loans carry collateral risk. If the borrower defaults, the lender may be able to repossess or sell the pledged asset according to the agreement and applicable law. Unsecured loans may not involve collateral, but default can still harm credit history and lead to collection or legal action.',
    },
  ],
  total_chunks: 25,
  embedding_dimension: 384,
  faiss_index_type: 'IndexFlatL2',
}

// Illustrative embedding preview - clearly labelled as such in the UI
export const ILLUSTRATIVE_EMBEDDING_PREVIEW = [
  0.0234, -0.1821, 0.0917, 0.4421, -0.0318, 0.2105, -0.3341, 0.1589,
  // ... (374 dimensions omitted)
  0.0853, 0.1172,
]

export const LOAN_CHUNKS = (() => {
  const text = STATIC_KB_INFO.documents[0].full_text
  const chunks = []
  let start = 0
  while (start < text.length) {
    chunks.push(text.slice(start, start + 300))
    start += 250
  }
  return chunks
})()
