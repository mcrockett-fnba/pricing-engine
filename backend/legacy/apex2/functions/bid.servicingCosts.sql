SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE       FUNCTION [bid].[servicingCosts]
(
    @itinStatus VARCHAR(10), 
    @creditScore INT, 
    @interestRate DECIMAL(15, 7), 
    @ltv DECIMAL(15, 4), 
    @loansize INT, 
    @interestratedelta DECIMAL(15, 4), 
    @collateralstate VARCHAR(2), 
    @lienposition INT, 
    @ratetype VARCHAR(5)
)
RETURNS TABLE
AS
RETURN
(
    WITH dimensions AS
    (
        SELECT 'creditBand' AS dimension, servicingCosts, itinStatus
        FROM bid.PrepaymentByCreditBand
        WHERE (@creditScore = 555 AND band = 'No Score') OR (@creditScore <> 555 AND @creditScore BETWEEN lowerLimit AND upperLimit)

        UNION ALL 

        SELECT 'interestRateBand', servicingCosts, itinStatus
        FROM bid.PrepaymentByInterestRateBand
        WHERE @interestRate BETWEEN lowerLimit AND upperLimit

        UNION ALL 

		SELECT 'ltvBand', servicingCosts, itinStatus
		FROM bid.PrepaymentByLtvBand
		WHERE CASE WHEN @ltv < 2.0 THEN @ltv * 100 ELSE @ltv END 
		BETWEEN lowerLimit AND upperLimit

        UNION ALL 

        SELECT 'loanSizeband', servicingCosts, itinStatus
        FROM bid.PrepaymentByLoanSizeBand
        WHERE @loansize BETWEEN lowerLimit AND upperLimit

        UNION ALL 

        SELECT 'interestRateDeltaBand', servicingCosts, itinStatus
        FROM bid.PrepaymentByInterestRateDeltaBand
        WHERE @interestratedelta BETWEEN lowerLimit AND upperLimit

        UNION ALL

        SELECT 'collateralState', servicingCosts, itinStatus
        FROM bid.PrepaymentByCollateralState
        WHERE band = @collateralstate

        UNION ALL 

        SELECT 'lienPosition', servicingCosts, itinStatus
        FROM bid.PrepaymentByLienPosition
        WHERE band = @lienposition

        UNION ALL 

        SELECT 'rateType', servicingCosts, itinStatus
        FROM bid.PrepaymentByRateType
        WHERE band = @ratetype
    ),
    filtered AS (
        SELECT * FROM dimensions WHERE itinStatus = @itinStatus
    ),
    avgVal AS (
        SELECT SUM(servicingCosts) * 1.0 / COUNT(*) AS overallAverage
        FROM filtered
    )
    SELECT 
        MAX(CASE WHEN dimension = 'creditBand' THEN servicingCosts END) AS creditBand,
        MAX(CASE WHEN dimension = 'interestRateBand' THEN servicingCosts END) AS interestRateBand,
        MAX(CASE WHEN dimension = 'ltvBand' THEN servicingCosts END) AS ltvBand,
        MAX(CASE WHEN dimension = 'loanSizeband' THEN servicingCosts END) AS loanSizeband,
        MAX(CASE WHEN dimension = 'interestRateDeltaBand' THEN servicingCosts END) AS interestRateDeltaBand,
        MAX(CASE WHEN dimension = 'collateralState' THEN servicingCosts END) AS collateralState,
        MAX(CASE WHEN dimension = 'lienPosition' THEN servicingCosts END) AS lienPosition,
        MAX(CASE WHEN dimension = 'rateType' THEN servicingCosts END) AS rateType,
        (SELECT overallAverage FROM avgVal) AS overallAverage
    FROM filtered
);
--runci
GO