SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE     VIEW [bid].[LoanPrePaymentRateDetail] AS

	WITH properties AS 
	(
	SELECT 
		account_number,
		year,
		month,
		state,
		lien_position,
		RANK()
		 OVER (PARTITION BY period,account_number
					ORDER BY CASE WHEN valuation_type_id = 1 THEN 1
					WHEN valuation_type_id = 2 THEN 2
					WHEN primary_property = 1 THEN 3
					ELSE 4
					END ,
					sort_order) AS ranking
	FROM relmeom.fnba.me_property_table_archive

	),
    armRates AS (
        SELECT 
            periodEndDate = EOMONTH(date_of_rate),
            year = DATEPART(YEAR, date_of_rate),
            month = DATEPART(MONTH, date_of_rate),
            Tnote_10_year,
            rowNumber = ROW_NUMBER() OVER (
                PARTITION BY EOMONTH(date_of_rate) 
                ORDER BY date_of_rate DESC
            )
        FROM notedb.fnba.arm_rates
        WHERE Tnote_10_year IS NOT NULL
    )

    SELECT 
        snap.account_number,
        snap.period,
        CASE WHEN itin.accountNumber IS NOT NULL THEN 'ITIN' ELSE 'Not ITIN' END AS itinStatus,
        CASE 
			WHEN snap.avg_original_credit = 555 THEN 'No Score'
            WHEN snap.avg_original_credit <= 575 THEN '< 576'
            WHEN snap.avg_original_credit <= 600 THEN '576-600'
            WHEN snap.avg_original_credit <= 625 THEN '601-625'
            WHEN snap.avg_original_credit <= 650 THEN '626-650'
            WHEN snap.avg_original_credit <= 675 THEN '651-675'
            WHEN snap.avg_original_credit <= 700 THEN '676-700'
            WHEN snap.avg_original_credit <= 725 THEN '701-725'
            WHEN snap.avg_original_credit <= 750 THEN '726-750'
            ELSE '>=751'
        END AS creditBand,
        CASE 
            WHEN snap.interest_rate < 2 THEN '<2.0'
            WHEN snap.interest_rate < 3 THEN '2.0-2.99'
            WHEN snap.interest_rate < 4 THEN '3.0-3.99'
            WHEN snap.interest_rate < 5 THEN '4.0-4.99'
            WHEN snap.interest_rate < 6 THEN '5.0-5.99'
            WHEN snap.interest_rate < 7 THEN '6.0-6.99'
            WHEN snap.interest_rate < 8 THEN '7.0-7.99'
            WHEN snap.interest_rate < 9 THEN '8.0-8.99'
            WHEN snap.interest_rate < 10 THEN '9.0-9.99'
            ELSE '>=10.0'
        END AS interestRateBand,
        CASE 
            WHEN nma.original_debt2income IS NULL THEN 'Not calculated'
            WHEN nma.original_debt2income <= 0.35 THEN '0 - 0.35'
            WHEN nma.original_debt2income <= 0.43 THEN '>0.35 - 0.43'
            WHEN nma.original_debt2income <= 0.50 THEN '>0.43 - 0.50'
            WHEN nma.original_debt2income <= 0.55 THEN '>0.50 - 0.55'
            WHEN nma.original_debt2income <= 0.60 THEN '>0.55 - 0.60'
            ELSE '>0.60'
        END AS dtiBand,
        CASE 
            WHEN nma.original_loan2value < 0.75 THEN '< 75%'
            WHEN nma.original_loan2value < 0.80 THEN '75% - 79.99%'
            WHEN nma.original_loan2value < 0.85 THEN '80% - 84.99%'
            WHEN nma.original_loan2value < 0.90 THEN '85% - 89.99%'
            ELSE '>= 90%'
        END AS ltvBand,
        CASE 
            WHEN nma.original_cust_balance < 50000 THEN '$0 - $49,999'
            WHEN nma.original_cust_balance < 100000 THEN '$50,000 - $99,999'
            WHEN nma.original_cust_balance < 150000 THEN '$100,000 - $149,999'
            WHEN nma.original_cust_balance < 200000 THEN '$150,000 - $199,999'
            WHEN nma.original_cust_balance < 250000 THEN '$200,000 - $249,999'
            WHEN nma.original_cust_balance < 500000 THEN '$250,000 - $499,999'
            WHEN nma.original_cust_balance < 1000000 THEN '$500,000 - $999,999'
            ELSE '$1,000,000+'
        END AS loanSizeBand,
		CASE
			WHEN snap.interest_rate - ar.Tnote_10_year <= -3 THEN '<=-3%'
			WHEN snap.interest_rate - ar.Tnote_10_year <= -2 THEN '-2 to -2.99%'
			WHEN snap.interest_rate - ar.Tnote_10_year <= -1 THEN '-1 to -1.99%'
			WHEN snap.interest_rate - ar.Tnote_10_year < 1 THEN '-0.99 to 0.99%'
			WHEN snap.interest_rate - ar.Tnote_10_year < 2 THEN '1 to 1.99%'
			WHEN snap.interest_rate - ar.Tnote_10_year < 3 THEN '2 to 2.99%'
			ELSE '>=3%'
		END AS interestRateDeltaBand,
		IIF(atrmethod.abilityToRepayMethodName IS NULL,'Unknown',atrmethod.abilityToRepayMethodName) AS abilityToRepayMethodName,
        IIF(states.state IS NULL, 'Not RE Secured',states.state) AS collateralState,
        ISNULL(NULLIF(snap.property_type, ''), 'Unsecured commercial loan') AS collateralType,
        ISNULL(snap.lien_position,1) AS lienPosition,
        IIF(arm.account_number IS NULL, 'FXD', 'ARM') AS rateType,
        pp.actualPaymentAmount,
        pp.expectedPaymentAmount,
		IIF(x.periodEndDate = x.priorPeriodEndDate, 1, 0) AS rolling1,
		IIF((x.periodEndDate >= EOMONTH(DATEADD(MONTH, -2, x.priorPeriodEndDate))), 1, 0) AS rolling3,
		IIF((x.periodEndDate >= EOMONTH(DATEADD(MONTH, -11, x.priorPeriodEndDate))), 1, 0) AS rolling12,
  		1 AS rollingAll,
		CASE 
			WHEN ns.note_status_master_id=5 THEN 1
			WHEN ns.note_status_master_id=1 THEN 1
			WHEN ns.note_status LIKE '%Sold Inventory%' THEN 1
			ELSE 0 
		END AS isCostOfDefault
    FROM  relmeom.fnba.me_notes_hist snap 
    JOIN notedb.fnba.note_master nm ON nm.account_number = snap.account_number
	AND snap.period >=200701
    JOIN notedb.fnba.officeDepartment officedep ON officedep.officeId = nm.office_id
    JOIN relmeom.fnba.me_note_master_archive nma ON nma.account_number = snap.account_number AND nma.year = snap.year AND nma.month = snap.month
    JOIN relmeom.performance.PaymentPerformance pp ON pp.accountNumber = snap.account_number AND pp.year = snap.year AND pp.month = snap.month
    LEFT JOIN armRates ar ON ar.year = snap.year AND ar.month = snap.month AND ar.rowNumber = 1
    LEFT JOIN reporting.fnba.accountsUnderwrittenAsItin itin ON itin.accountNumber = snap.account_number
    LEFT JOIN notedb.fnba.accountAbilityToRepayMethod atrAccounts ON atrAccounts.accountNumber = snap.account_number
    LEFT JOIN notedb.fnba.abilityToRepayMethods atrmethod ON atrmethod.abilityToRepayMethodId = atrAccounts.abilityToRepayMethodId
	LEFT JOIN properties prop ON prop.account_number = snap.account_number AND prop.ranking = 1 AND prop.year = snap.year AND prop.month = snap.month
	LEFT JOIN (SELECT DISTINCT account_number FROM notedb.fnba.arm_accounts) arm ON arm.account_number = snap.account_number
	LEFT JOIN notedb.fnba.state_code states ON states.state = prop.state
	LEFT JOIN notedb.fnba.note_status ns ON ns.note_status_id = nm.note_status_id
	CROSS APPLY(SELECT EOMONTH(CONVERT(DATE, CONCAT(snap.period, '01'), 112)), EOMONTH(GETDATE(), -1)) AS x(periodEndDate, priorPeriodEndDate)
    WHERE 0 = 0 
	AND officedep.departmentId IN (1,3,4) 
	AND (officedep.departmentId <> 1 OR nm.trans_type_id = 1) 
	AND nm.paper_type_id <> 69
	AND nma.office_id NOT IN (1008,1009)
GO